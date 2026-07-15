"""B-646: Waveform-Blob-Parse im Kind-Prozess statt im QThread.

Live-belegt 2026-07-15: ``WaveformLoadWorker.run()`` lief zwar in einem
eigenen QThread, aber ``json.loads()`` auf grossen Waveform-Blobs (langer
Audio-Track) hielt den GIL durchgehend — der Watchdog mass einen echten
Main-Thread-Freeze von 1.8-2.5s trotz Thread-Isolation. Fix: der Query+Parse
laeuft jetzt in einem eigenen Prozess (gleiches Muster wie B-618
Cluster-Fit-Subprozess), der Aufrufer faellt bei Subprozess-Fehlern auf den
alten In-Process-Pfad zurueck.

Mock-Tests pruefen die Dispatch-/Fallback-Logik in ``ui/timeline.py``
(analog ``tests/enrichment/test_umap_warmup.py``). Ein echter (nicht
gemockter) End-to-End-Test prueft den ``PB_WAVEFORM_PARSE``-Entrypoint in
``main.py`` gegen eine echte SQLite-Test-DB.
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - Qt missing
    pytest.skip("Qt not available", allow_module_level=True)

_app = QApplication.instance() or QApplication([])

from ui.timeline import WaveformLoadWorker  # noqa: E402


# ── Dispatch / Fallback (gemockt) ─────────────────────────────────────────────


def test_run_uses_subprocess_result_when_available(monkeypatch):
    """Subprozess liefert Ergebnis -> In-Process-Pfad darf NICHT laufen."""
    worker = WaveformLoadWorker(media_id=42)
    sentinel = (True, [1.0], [2.0], [3.0], [4.0])
    monkeypatch.setattr(worker, "_run_subprocess", lambda: sentinel)

    def _boom():
        raise AssertionError("In-Process-Pfad darf nicht laufen, wenn Subprozess liefert")

    monkeypatch.setattr(worker, "_run_inprocess", _boom)

    received: list = []
    worker.finished.connect(lambda *a: received.append(a))
    worker.run()

    assert received == [sentinel]


def test_run_falls_back_to_inprocess_when_subprocess_returns_none(monkeypatch):
    """Subprozess liefert None (z.B. Fehler intern abgefangen) -> Fallback."""
    worker = WaveformLoadWorker(media_id=42)
    monkeypatch.setattr(worker, "_run_subprocess", lambda: None)
    sentinel = (True, [9.0], [8.0], [7.0], [6.0])
    monkeypatch.setattr(worker, "_run_inprocess", lambda: sentinel)

    received: list = []
    worker.finished.connect(lambda *a: received.append(a))
    worker.run()

    assert received == [sentinel]


@pytest.mark.parametrize(
    "side_effect",
    [
        subprocess.CalledProcessError(1, ["python", "main.py"]),
        subprocess.TimeoutExpired(["python", "main.py"], 30.0),
        OSError("exe not found"),
    ],
)
def test_run_falls_back_to_inprocess_on_subprocess_exception(monkeypatch, side_effect):
    """Subprozess wirft (Crash/Timeout/OS-Fehler) -> kein Raise, Fallback greift."""
    worker = WaveformLoadWorker(media_id=42)

    def _raise():
        raise side_effect

    monkeypatch.setattr(worker, "_run_subprocess", _raise)
    sentinel = (True, [1.0], [1.0], [1.0], [])
    monkeypatch.setattr(worker, "_run_inprocess", lambda: sentinel)

    received: list = []
    worker.finished.connect(lambda *a: received.append(a))
    worker.run()  # darf nicht raisen

    assert received == [sentinel]


def test_run_subprocess_dispatches_correct_job_and_reads_pickle(monkeypatch, tmp_path):
    """_run_subprocess: Job-Datei korrekt befuellt, Ergebnis aus Pickle gelesen."""
    from ui import timeline as tlmod

    worker = WaveformLoadWorker(media_id=7)
    monkeypatch.setattr(tlmod, "APP_ROOT", tmp_path, raising=False)
    # APP_ROOT wird lazy importiert in _run_subprocess (from database.session
    # import APP_ROOT) — monkeypatch dort, wo tatsaechlich gelesen wird.
    import database.session as db_session_mod
    monkeypatch.setattr(db_session_mod, "APP_ROOT", tmp_path, raising=False)

    calls: list = []
    expected_result = (True, [1.0, 2.0], [3.0], [4.0], [5.0])

    def _fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        # Job-Datei einlesen (env enthaelt PB_WAVEFORM_PARSE -> job.json Pfad)
        job_path = kwargs["env"]["PB_WAVEFORM_PARSE"]
        with open(job_path, "r", encoding="utf-8") as jf:
            job = json.load(jf)
        assert job["media_id"] == 7
        assert job["project_path"] == str(tmp_path)
        # Simuliert das, was main.py's Entrypoint schreiben wuerde.
        with open(job["out"], "wb") as of:
            pickle.dump(expected_result, of)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = worker._run_subprocess()

    assert result == expected_result
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[0] == sys.executable
    assert kwargs.get("check") is True
    assert kwargs.get("timeout") == tlmod._WAVEFORM_SUBPROCESS_TIMEOUT_S


# ── Echter End-to-End-Test: main.py PB_WAVEFORM_PARSE-Entrypoint ─────────────


def _build_project_with_waveform(tmp_path):
    """Baut ein minimales echtes Projekt (pb_studio.db) mit einem
    AudioTrack + WaveformData + Beatgrid, um den echten Entrypoint zu testen."""
    from sqlalchemy.orm import Session as DBSession

    from database.models import AudioTrack, Base, Beatgrid, Project, WaveformData
    from database.session import make_nullpool_engine

    project_dir = tmp_path / "b646_project"
    project_dir.mkdir()
    db_path = project_dir / "pb_studio.db"
    engine = make_nullpool_engine(f"sqlite:///{db_path}", enable_foreign_keys=True)
    Base.metadata.create_all(engine)

    with DBSession(engine) as s:
        p = Project(name="b646", path=str(project_dir))
        s.add(p)
        s.flush()
        track = AudioTrack(project_id=p.id, file_path="/tmp/b646.wav", title="B646 Audio")
        s.add(track)
        s.flush()
        s.add(WaveformData(
            audio_track_id=track.id,
            band_low=json.dumps([0.1, 0.2, 0.3]),
            band_mid=json.dumps([0.4, 0.5]),
            band_high=json.dumps([0.6]),
        ))
        s.add(Beatgrid(
            audio_track_id=track.id,
            bpm=128.0,
            beat_positions=json.dumps([0.5, 1.0, 1.5]),
        ))
        s.commit()
        track_id = track.id

    engine.dispose()
    return project_dir, track_id


def test_main_py_waveform_parse_entrypoint_real_subprocess(tmp_path):
    """Echter (nicht gemockter) Subprozess-Aufruf gegen echte Test-DB.

    Langsamer als die Mock-Tests (voller Interpreter-Start + main.py-Imports),
    aber deckt genau die Stelle ab, die die Mock-Tests NICHT pruefen: dass der
    PB_WAVEFORM_PARSE-Entrypoint in main.py selbst syntaktisch/funktional
    korrekt ist (set_project, Query, JSON-Parse, Pickle-Dump).
    """
    project_dir, track_id = _build_project_with_waveform(tmp_path)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main_py = os.path.join(repo_root, "main.py")
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "res.pkl"
    with open(job_path, "w", encoding="utf-8") as jf:
        json.dump(
            {"project_path": str(project_dir), "media_id": track_id, "out": str(out_path)},
            jf,
        )

    env = {**os.environ, "PB_WAVEFORM_PARSE": str(job_path), "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.run(
        [sys.executable, main_py],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert out_path.exists()
    with open(out_path, "rb") as of:
        result = pickle.load(of)

    ok, band_low, band_mid, band_high, beat_positions = result
    assert ok is True
    assert band_low == [0.1, 0.2, 0.3]
    assert band_mid == [0.4, 0.5]
    assert band_high == [0.6]
    assert beat_positions == [0.5, 1.0, 1.5]
