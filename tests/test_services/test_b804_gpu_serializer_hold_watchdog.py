"""B-804 — Hold-Watchdog des GpuSerializer.

Vorfall 2026-08-11 19:31:50: Worker A hatte den Serializer als ``render``
gegriffen, danach 27 Minuten absolute Stille — kein Fortschritt, kein
ffmpeg, keine einzige Logzeile, kein Stack. Die B-503-Absicherung deckt
nur die WARTE-Seite ab (`acquire`-Timeout + 30s-Holder-WARNING); ein
Halter, der nie zurueckkommt, war unbeobachtet.

Diese Tests pruefen die Absicherung:
* ueberfaelliger Halter wird gemeldet UND mit Thread-Stacks in eine Datei
  gedumpt (Datei, weil beim Vorfall auch die Logging-Kette stumm war),
* der Watchdog greift NICHT ein (kein Force-Release, keine Exception),
* die B-503-Timeout-Semantik der Warte-Seite bleibt unveraendert.
"""
from __future__ import annotations

import threading
import time

import pytest

from services.brain.gpu_serializer import GpuSerializer


def _make(tmp_path, monkeypatch, warn_s=0.3):
    dump = tmp_path / "gpu_serializer_stalls.log"
    monkeypatch.setenv("PB_GPU_STALL_DUMP", str(dump))
    s = GpuSerializer(
        name="b804_test",
        empty_cache_on_release=False,
        hold_warn_s=warn_s,
        hold_poll_s=0.02,
    )
    return s, dump


def test_ueberfaelliger_halter_wird_gemeldet_und_gedumpt(tmp_path, monkeypatch, caplog):
    s, dump = _make(tmp_path, monkeypatch)
    caplog.set_level("ERROR", logger="services.brain.gpu_serializer")

    with s.acquire("render"):
        deadline = time.monotonic() + 5.0
        while s.stall_reports == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        # Der Lock ist waehrend der Meldung weiterhin gehalten — der
        # Watchdog beobachtet, er greift nicht ein.
        assert s.is_locked()
        assert s.current_holder() == "render"

    assert s.stall_reports >= 1, "Hold-Watchdog hat den ueberfaelligen Halter nicht gemeldet"
    assert dump.exists(), "kein Stack-Dump geschrieben"
    text = dump.read_text(encoding="utf-8")
    assert "GPU-SERIALIZER STALL" in text
    assert "holder='render'" in text
    assert "--- Thread " in text
    assert any("haelt den Lock seit" in r.getMessage() for r in caplog.records)


def test_watchdog_bricht_den_ablauf_nicht_ab(tmp_path, monkeypatch):
    """Nach der Meldung laeuft der Halter normal weiter und gibt sauber frei."""
    s, dump = _make(tmp_path, monkeypatch)
    finished = []
    with s.acquire("render"):
        deadline = time.monotonic() + 5.0
        while s.stall_reports == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        finished.append("body-completed")
    assert finished == ["body-completed"]
    assert not s.is_locked()
    assert s.current_holder() is None


def test_kein_fehlalarm_bei_kurzen_haltezeiten(tmp_path, monkeypatch):
    s, _dump = _make(tmp_path, monkeypatch, warn_s=5.0)
    with s.acquire("render"):
        time.sleep(0.2)
    time.sleep(0.1)
    assert s.stall_reports == 0


def test_b503_timeout_semantik_unveraendert(tmp_path, monkeypatch):
    """Warte-Seite: acquire-Timeout wirft weiterhin TimeoutError mit Holder-Info."""
    s, _dump = _make(tmp_path, monkeypatch, warn_s=0.2)
    holding = threading.Event()
    release = threading.Event()

    def _holder():
        with s.acquire("render"):
            holding.set()
            release.wait(5.0)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    assert holding.wait(5.0)
    try:
        with pytest.raises(TimeoutError) as exc:
            with s.acquire("second", timeout=0.3):
                pass
        assert "render" in str(exc.value)
    finally:
        release.set()
        t.join(5.0)
    assert not s.is_locked()
