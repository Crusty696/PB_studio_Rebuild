"""B-789: pull_ollama_model meldete Erfolg, bevor der Download lief.

Vertraege:
(a) Erfolg wird erst nach Abschluss des Pulls gemeldet.
(b) Ein Fehlschlag wird als Fehlschlag gemeldet, nicht als Erfolg.
(c) Progress-Events kommen weiterhin an.
(d) Der Erfolgsfall aus B-299 (Registry-Zeile 'installed') bleibt intakt.
"""

import io
import json
import threading
import time
import urllib.error

import pytest
from sqlalchemy.orm import Session

from database import ModelRegistry
from services import model_lifecycle_service as mls


class _FakeResponse(io.BytesIO):
    """Streamt vorbereitete NDJSON-Zeilen mit Verzoegerung pro Zeile."""

    def __init__(self, lines: list[dict], delay: float = 0.0):
        super().__init__()
        self._lines = lines
        self._delay = delay
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for chunk in self._lines:
            if self._delay:
                time.sleep(self._delay)
            yield (json.dumps(chunk) + "\n").encode()

    def read(self, *_args):
        return json.dumps({"models": []}).encode()


def _install_fake_urlopen(monkeypatch, pull_response, tags_models=None):
    """Ersetzt urlopen im Service: /api/pull -> pull_response, /api/tags -> Liste."""
    tags_models = tags_models or []

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/pull" in url:
            if isinstance(pull_response, Exception):
                raise pull_response
            return pull_response
        return _FakeResponse([])

    monkeypatch.setattr(mls.urllib.request, "urlopen", _fake_urlopen)


def test_pull_returns_only_after_stream_completed(test_engine, monkeypatch) -> None:
    """(a) + (c): Rueckgabe erst nach dem letzten Progress-Event."""
    lines = [
        {"status": "pulling manifest"},
        {"status": "downloading", "total": 100, "completed": 50},
        {"status": "downloading", "total": 100, "completed": 100},
        {"status": "success"},
    ]
    _install_fake_urlopen(monkeypatch, _FakeResponse(lines, delay=0.05))

    events = []
    svc = mls.ModelLifecycleService()
    t0 = time.time()
    ok = svc.pull_ollama_model("fake-model:1b", progress_cb=events.append)
    elapsed = time.time() - t0

    assert ok is True
    # Der Stream braucht >= 4 * 0.05 s; ein Rueckkehren nach ~0 s hiesse
    # "Erfolg gemeldet, bevor der Download lief" (B-789).
    assert elapsed >= 0.15, f"kehrte nach {elapsed:.3f}s zurueck — zu frueh"
    # (c) Progress-Events sind angekommen, und zwar VOR der Rueckgabe.
    assert len(events) >= len(lines), f"nur {len(events)} progress-Events"
    assert events[-1].finished is True


def test_pull_reports_http_failure_as_failure(test_engine, monkeypatch) -> None:
    """(b) HTTP-/Netzwerkfehler -> False, nicht True."""
    _install_fake_urlopen(
        monkeypatch,
        urllib.error.URLError("connection refused"),
    )

    svc = mls.ModelLifecycleService()
    events = []
    ok = svc.pull_ollama_model("fake-broken:1b", progress_cb=events.append)

    assert ok is False
    assert events and events[-1].finished is True
    assert events[-1].error


def test_pull_reports_stream_error_chunk_as_failure(test_engine, monkeypatch) -> None:
    """(b) Ollama liefert HTTP 200 + {"error": ...} -> muss False sein."""
    lines = [
        {"status": "pulling manifest"},
        {"error": "pull model manifest: file does not exist"},
    ]
    _install_fake_urlopen(monkeypatch, _FakeResponse(lines))

    svc = mls.ModelLifecycleService()
    ok = svc.pull_ollama_model("does-not-exist:1b")

    assert ok is False

    with Session(test_engine) as session:
        row = session.query(ModelRegistry).filter_by(
            model_id="does-not-exist:1b"
        ).one()
        assert row.status == "error"


def test_pull_without_success_status_is_failure(test_engine, monkeypatch) -> None:
    """(b) Abgebrochener Stream ohne Erfolgsmeldung ist kein Erfolg."""
    lines = [
        {"status": "pulling manifest"},
        {"status": "downloading", "total": 100, "completed": 30},
    ]
    _install_fake_urlopen(monkeypatch, _FakeResponse(lines))

    svc = mls.ModelLifecycleService()
    assert svc.pull_ollama_model("truncated:1b") is False


def test_b299_success_path_still_writes_installed_registry_row(
    test_engine, monkeypatch
) -> None:
    """(d) Erfolgsfall unveraendert: Registry-Zeile + Progress + True."""
    lines = [
        {"status": "downloading", "total": 10, "completed": 10},
        {"status": "success"},
    ]

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url
        if "/api/pull" in url:
            return _FakeResponse(lines)
        return _FakeResponse(
            [],
        )

    monkeypatch.setattr(mls.urllib.request, "urlopen", _fake_urlopen)

    events = []
    svc = mls.ModelLifecycleService()
    ok = svc.pull_ollama_model("b299-model:1b", progress_cb=events.append)

    assert ok is True
    assert any(e.progress == 1.0 for e in events)

    with Session(test_engine) as session:
        row = session.query(ModelRegistry).filter_by(
            model_id="b299-model:1b"
        ).one()
    assert row.status == "downloading"


def test_wait_false_keeps_non_blocking_contract(test_engine, monkeypatch) -> None:
    """wait=False behaelt die alte Semantik (sofortige Rueckkehr)."""
    _install_fake_urlopen(
        monkeypatch, _FakeResponse([{"status": "success"}], delay=0.3)
    )

    svc = mls.ModelLifecycleService()
    t0 = time.time()
    ok = svc.pull_ollama_model("nonblocking:1b", wait=False)
    elapsed = time.time() - t0

    assert ok is True
    assert elapsed < 0.2
    # Aufraeumen: Hintergrund-Thread auslaufen lassen.
    for _ in range(50):
        if not svc.is_download_active("nonblocking:1b"):
            break
        time.sleep(0.05)


@pytest.mark.parametrize("_run", [0])
def test_no_thread_leak_after_blocking_pull(test_engine, monkeypatch, _run) -> None:
    """Nach dem blockierenden Pull laeuft kein Pull-Thread mehr."""
    _install_fake_urlopen(monkeypatch, _FakeResponse([{"status": "success"}]))

    svc = mls.ModelLifecycleService()
    svc.pull_ollama_model("leakcheck:1b")

    assert svc.is_download_active("leakcheck:1b") is False
    assert not [
        t for t in threading.enumerate() if t.name == "ollama-pull-leakcheck:1b"
    ]
