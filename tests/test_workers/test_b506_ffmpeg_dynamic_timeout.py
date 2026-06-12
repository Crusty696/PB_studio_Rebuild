"""B-506: Dynamische FFmpeg-Timeouts statt statischem 600s-Per-File-Kill.

Deckt ab:
1. Helper-Mathematik ``ffmpeg_timeout_for`` (None/0/ungueltig/kurz/3h,
   custom min_sec/factor).
2. Verdrahtung ``BatchConvertWorker``: 3h-Quelle → timeout 32400 an
   ``_run_batch_ffmpeg_cancellable``; Dauer unbekannt → 600.
3. Verdrahtung ``ProxyCreationWorker``: 3h-Quelle → timeout 32400 an
   ``convert_service.convert``.
"""
from __future__ import annotations

import subprocess
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# 1: Helper-Mathematik
# ---------------------------------------------------------------------------

def test_ffmpeg_timeout_for_unknown_duration_returns_min():
    from services.timeout_constants import ffmpeg_timeout_for

    assert ffmpeg_timeout_for(None) == 600.0
    assert ffmpeg_timeout_for(0) == 600.0
    assert ffmpeg_timeout_for(-5) == 600.0
    assert ffmpeg_timeout_for("kaputt") == 600.0


def test_ffmpeg_timeout_for_short_source_keeps_min_floor():
    from services.timeout_constants import ffmpeg_timeout_for

    # 60 s * 3 = 180 < 600 → Untergrenze greift
    assert ffmpeg_timeout_for(60) == 600.0
    # exakt an der Grenze: 200 s * 3 = 600
    assert ffmpeg_timeout_for(200) == 600.0


def test_ffmpeg_timeout_for_three_hour_source():
    from services.timeout_constants import ffmpeg_timeout_for

    # 3 h = 10800 s → 3× = 32400 s (vorher: nach 600 s gekillt)
    assert ffmpeg_timeout_for(10800) == 32400.0


def test_ffmpeg_timeout_for_custom_min_and_factor():
    from services.timeout_constants import ffmpeg_timeout_for

    assert ffmpeg_timeout_for(300, min_sec=100.0, factor=2.0) == 600.0
    assert ffmpeg_timeout_for(10, min_sec=100.0, factor=2.0) == 100.0


# ---------------------------------------------------------------------------
# 2: BatchConvertWorker-Verdrahtung
# ---------------------------------------------------------------------------

def _run_batch_convert(tmp_path, monkeypatch, probed_duration):
    import workers.import_export as ie

    src = tmp_path / "video.mp4"
    src.write_bytes(b"video")

    monkeypatch.setattr(ie, "_ffprobe_duration", lambda path: probed_duration)
    captured = {}

    def fake_runner(cmd, cancel_check=None, timeout=None, progress_cb=None):
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ie, "_run_batch_ffmpeg_cancellable", fake_runner)

    worker = ie.BatchConvertWorker(
        [{"file_path": str(src)}], "1280x720", "30", "libx264", ".mp4",
    )
    # _run_locked direkt — GPU_EXECUTION_LOCK ist fuer den Timeout-Test
    # irrelevant und wuerde nur model_manager-Import ziehen.
    worker._run_locked()
    return captured


def test_batch_convert_three_hour_source_gets_32400(tmp_path, monkeypatch):
    captured = _run_batch_convert(tmp_path, monkeypatch, probed_duration=10800.0)
    assert captured["timeout"] == 32400.0


def test_batch_convert_unknown_duration_keeps_default_600(tmp_path, monkeypatch):
    captured = _run_batch_convert(tmp_path, monkeypatch, probed_duration=0.0)
    assert captured["timeout"] == 600.0


# ---------------------------------------------------------------------------
# 3: ProxyCreationWorker-Verdrahtung
# ---------------------------------------------------------------------------

def _run_proxy_creation(tmp_path, monkeypatch, probed_duration):
    import database
    import services.convert_service as cs
    import workers.import_export as ie

    src = tmp_path / "video.mp4"
    src.write_bytes(b"video")

    monkeypatch.setattr(ie, "_ffprobe_duration", lambda path: probed_duration)
    captured = {}

    def fake_convert(input_path, preset_name=None, progress_cb=None,
                     cancel_check=None, timeout=None, **kwargs):
        captured["timeout"] = timeout
        return str(tmp_path / "proxy.mp4")

    monkeypatch.setattr(cs, "convert", fake_convert)

    @contextmanager
    def fake_session():
        session = MagicMock()
        session.get.return_value = None  # Clip nicht gefunden → kein commit
        yield session

    monkeypatch.setattr(database, "nullpool_session", fake_session)

    worker = ie.ProxyCreationWorker(clip_id=1, video_path=str(src))
    worker._run_with_slot()
    return captured


def test_proxy_creation_three_hour_source_gets_32400(tmp_path, monkeypatch):
    captured = _run_proxy_creation(tmp_path, monkeypatch, probed_duration=10800.0)
    assert captured["timeout"] == 32400.0


def test_proxy_creation_unknown_duration_keeps_default_600(tmp_path, monkeypatch):
    captured = _run_proxy_creation(tmp_path, monkeypatch, probed_duration=0.0)
    assert captured["timeout"] == 600.0
