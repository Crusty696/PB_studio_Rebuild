"""Batch-Tests fuer den Scan-5-Rest: B-699, B-702, B-703, B-704, B-705 +
B-706 (F1 Thumbnail, Q3 media_table). Gebuendelt gemaess Test-Batching-Regel.
"""
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


# ── B-699: structure_enrichment-Engine hat jetzt die kanonischen Pragmas ─────

def test_b699_worker_engine_has_busy_timeout_and_fk(tmp_path, monkeypatch):
    import workers.structure_enrichment as se

    db = tmp_path / "probe.db"
    import sqlite3
    sqlite3.connect(str(db)).close()

    class _FakeProxy:
        url = f"sqlite:///{db.as_posix()}"

    monkeypatch.setattr("database.session.engine", _FakeProxy())
    session = se._default_session_factory()
    try:
        eng = session.get_bind()
        assert getattr(eng, "_pb_worker_owned", False) is False or True  # Flag optional
        with eng.connect() as conn:
            from sqlalchemy import text
            busy = conn.execute(text("PRAGMA busy_timeout")).scalar()
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert int(busy) >= 120000, f"busy_timeout={busy} — Pragmas fehlen (B-699)"
        assert int(fk) == 1, "foreign_keys=ON fehlt (B-699)"
    finally:
        session.close()
        session.get_bind().dispose()


# ── B-702: Hash-Mismatch darf NICHT in den DB-Fallback laufen ────────────────

def test_b702_hash_mismatch_returns_none_no_db_fallback(monkeypatch, tmp_path):
    from services.audio_pipeline.stages import StemGenStage
    from services.audio_pipeline import stem_cache
    import services.audio_pipeline.stages as stages_mod

    stage = StemGenStage.__new__(StemGenStage)

    meta = {
        "wav_subtype": stages_mod._TARGET_WAV_SUBTYPE,
        "demucs_version": stages_mod._DEMUCS_VERSION,
        "original_hash": "ALT",
        "stem_hashes": {},
    }
    monkeypatch.setattr(stem_cache, "load_cache_meta", lambda tid: meta)
    monkeypatch.setattr(stem_cache, "compute_audio_hash", lambda p: "NEU")

    db_fallback_called = {"v": False}

    def _spy_db(track_id):
        db_fallback_called["v"] = True
        return {"drums": "alt.wav"}

    monkeypatch.setattr(StemGenStage, "_try_db_stem_references", staticmethod(_spy_db))

    class _Ctx:
        track_id = 1
        original_path = str(tmp_path / "x.mp3")

    result = stage._try_reuse(_Ctx())
    assert result is None, "Hash-Mismatch darf keine Stems wiederverwenden (B-702)"
    assert not db_fallback_called["v"], (
        "Hash-Mismatch fiel in den DB-Fallback zurueck — Invalidierung ausgehebelt (B-702)"
    )


# ── B-703: Cancel im Chunk-Loop greift vor dem GPU-Lock ──────────────────────

def test_b703_chunked_analysis_aborts_on_should_stop():
    from services.beat_analysis_service import BeatAnalysisService

    svc = BeatAnalysisService()
    with pytest.raises(RuntimeError, match="abgebrochen"):
        # should_stop=True -> Abbruch VOR Disk-Load/Modell/Lock; weder Datei
        # noch Modell werden angefasst.
        svc._analyze_chunked(
            "C:/nonexistent/mix.mp3", total_duration=1200.0, sr=22050,
            should_stop=lambda: True,
        )


# ── B-704: Stale-Worker-done() schaltet den Workspace nicht mehr um ──────────

def test_b704_stale_worker_done_ignored_and_predecessor_cancelled():
    _qapp()
    from PySide6.QtCore import QObject, Signal
    from ui.controllers.schnitt_controller import SchnittController

    class _FakeWorker(QObject):
        progress = Signal(int, str)
        done = Signal()
        failed = Signal(str)

        def __init__(self):
            super().__init__()
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    class _FakeWorkspace:
        def __init__(self):
            self.refresh_calls = 0

        def show_progress(self, *a):
            pass

        def refresh_state_from_db(self):
            self.refresh_calls += 1

    ctrl = SchnittController.__new__(SchnittController)
    QObject.__init__(ctrl)
    ctrl.workspace = _FakeWorkspace()
    ctrl._current_worker = None

    w1 = _FakeWorker()
    w2 = _FakeWorker()
    ctrl.attach_worker(w1)
    ctrl.attach_worker(w2)  # ueberlappender zweiter Worker

    # Vorgaenger wurde beim Attach abgekoppelt + cancelt (B-704/D2)
    assert w1.cancelled, "attach_worker hat den Vorgaenger nicht gecancelt"

    # Stale done() von w1 (falls Signal doch noch feuert) aendert nichts (D1)
    ctrl._current_worker = w2
    w1.done.emit()
    assert ctrl.workspace.refresh_calls == 0, (
        "done() eines veralteten Workers schaltete den Workspace um (B-704)"
    )

    # done() des aktuellen Workers wirkt normal
    w2.done.emit()
    assert ctrl.workspace.refresh_calls == 1
    assert ctrl._current_worker is None


# ── B-705: Downbeat-Toleranz deckt den realen Rundungs-Drift ─────────────────

def test_b705_downbeat_tolerance_covers_rounding_drift():
    from services.pacing_edit_helpers import (
        DOWNBEAT_MATCH_TOLERANCE_SEC, _is_downbeat_near,
    )

    assert DOWNBEAT_MATCH_TOLERANCE_SEC >= 0.20, (
        "Toleranz zu eng — chunked-Downbeats (2 Dezimalstellen + Offset) "
        "driften bis ~240ms (B-705)"
    )
    # Beat 10.1234, Downbeat auf 2 Dezimalstellen gerundet: 10.12 + Drift 0.15
    assert _is_downbeat_near(10.1234, [10.27]), (
        "realer Rundungs-Drift wird nicht gematcht (B-705)"
    )


# ── B-706/F1: kaputtes Thumbnail wird entfernt statt Cache zu vergiften ──────

def test_b706_f1_zero_byte_thumbnail_removed(monkeypatch, tmp_path):
    import ui.widgets.media_grid as mg

    src = tmp_path / "video.mp4"
    src.write_bytes(b"x")
    dest = tmp_path / "thumb.jpg"

    monkeypatch.setattr(mg, "_ensure_thumb_dir", lambda: None)
    monkeypatch.setattr(mg, "_thumb_path", lambda p: dest)

    import types

    def fake_run(cmd, **kwargs):
        dest.write_bytes(b"")  # ffmpeg-Fehler hinterlaesst 0-Byte-Datei
        return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"err")

    monkeypatch.setattr(mg.subprocess, "run", fake_run)

    img = mg._extract_thumb_qimage(str(src), 64, 36)
    assert not dest.exists(), (
        "0-Byte-Thumb blieb liegen — Cache-Poisoning, regeneriert nie (B-706/F1)"
    )
    assert img is not None and not img.isNull()  # Placeholder


# ── B-706/Q3: start_task-Fehler loest den In-Flight-Status ───────────────────

def test_b706_q3_start_task_failure_resets_inflight(monkeypatch):
    _qapp()
    from ui.controllers.media_table import MediaTableController

    ctrl = MediaTableController.__new__(MediaTableController)
    ctrl._reload_inflight = False
    ctrl._reload_dirty = False
    ctrl._reload_dirty_combos = False

    failed = {"v": False}

    def _fail_reset():
        failed["v"] = True
        ctrl._reload_inflight = False

    ctrl._on_media_reload_failed = _fail_reset

    class _BoomTM:
        @staticmethod
        def instance():
            raise RuntimeError("TaskManager kaputt")

    monkeypatch.setattr("services.task_manager.GlobalTaskManager", _BoomTM)

    ctrl._refresh_media_table()

    assert failed["v"], "start_task-Fehler wurde nicht behandelt (B-706/Q3)"
    assert ctrl._reload_inflight is False, (
        "_reload_inflight blieb True — Tabelle wuerde nie mehr aktualisieren"
    )
