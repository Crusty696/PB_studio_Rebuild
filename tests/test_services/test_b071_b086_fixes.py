"""Verify-Tests fuer B-071 und B-086.

- B-071: Phase-Refactor-Progress-Range bei >100 Videos im Batch — Float-
  Akkumulator statt int(100/total_videos)=0.
- B-086: LUFS-Normalisierung gibt jetzt Progress-Updates ueber stdout
  ``-progress pipe:1`` aus, statt UI fuer 2-4 Min einzufrieren.
"""

from __future__ import annotations

import inspect

import pytest


# --------------------------------------------------------------------------
# B-071: Float-Akkumulator
# --------------------------------------------------------------------------

def test_b071_video_worker_progress_uses_float_math() -> None:
    """``workers/video.py:VideoAnalysisPipelineWorker.run`` nutzt Float-
    Math fuer den Progress-Akkumulator — kein ``int(100/total_videos)``
    mehr (das war 0 sobald total_videos > 100)."""
    from workers import video as video_worker

    src = inspect.getsource(video_worker.VideoAnalysisPipelineWorker)
    assert "B-071" in src, "B-071-Marker fehlt in VideoAnalysisPipelineWorker"
    # Negativ-Snapshot: kein int(100 / total_videos)
    assert "int(100 / total_videos)" not in src, (
        "B-071: int(100/total_videos) ist immer noch da — bei >100 Videos = 0"
    )
    # Float-Akkumulator-Pattern muss vorhanden sein
    assert "((idx - 1) + pct" in src or "((_i - 1) + pct" in src, (
        "B-071: kein Float-Akkumulator (((idx-1) + pct/100) / total) im Lambda"
    )


# --------------------------------------------------------------------------
# B-086: LUFS-Progress
# --------------------------------------------------------------------------

def test_b086_normalize_audio_lufs_accepts_progress_cb() -> None:
    """``_normalize_audio_lufs`` hat ``progress_cb`` und ``total_duration``
    Parameter — Vorbedingung fuer Progress-Streaming."""
    from services import export_service

    sig = inspect.signature(export_service._normalize_audio_lufs)
    params = sig.parameters
    assert "progress_cb" in params, (
        "B-086: _normalize_audio_lufs hat kein progress_cb-Parameter"
    )
    assert "total_duration" in params, (
        "B-086: _normalize_audio_lufs hat kein total_duration-Parameter"
    )


def test_b086_normalize_audio_lufs_uses_progress_pipe() -> None:
    """``-progress pipe:1`` muss in beiden FFmpeg-Calls (Pass1+Pass2) gesetzt
    sein, sonst gibt FFmpeg keinen ``out_time_ms`` aus stdout."""
    from services import export_service

    src = inspect.getsource(export_service._normalize_audio_lufs)
    # Pass 1 + Pass 2 → mindestens 2x das Pattern
    assert src.count('"-progress"') >= 2, (
        "B-086: -progress pipe:1 fehlt in einem oder beiden FFmpeg-Calls"
    )
    assert src.count('"pipe:1"') >= 2


def test_b086_run_subprocess_supports_progress_streaming() -> None:
    """Helper akzeptiert ``progress_cb``, ``total_duration``, sowie
    ``progress_base_pct`` + ``progress_range_pct`` fuer Pass1/Pass2-Mapping."""
    from services import export_service

    sig = inspect.signature(export_service._run_subprocess_cancellable)
    params = sig.parameters
    for required in (
        "progress_cb", "total_duration", "progress_base_pct", "progress_range_pct",
    ):
        assert required in params, (
            f"B-086: _run_subprocess_cancellable hat kein {required}-Parameter"
        )


def test_b086_prepare_normalized_audio_probes_duration() -> None:
    """``_prepare_normalized_audio`` ruft ``_probe_audio_duration`` und
    reicht den Wert + den Caller-progress_cb an ``_normalize_audio_lufs`` weiter."""
    from services import export_service

    src = inspect.getsource(export_service._prepare_normalized_audio)
    assert "_probe_audio_duration" in src, (
        "B-086: _prepare_normalized_audio probed nicht die Audio-Duration"
    )
    assert "total_duration=" in src, (
        "B-086: _prepare_normalized_audio reicht total_duration nicht durch"
    )
    assert "progress_cb=" in src, (
        "B-086: _prepare_normalized_audio reicht progress_cb nicht durch"
    )


def test_b086_probe_audio_duration_returns_zero_on_failure(tmp_path) -> None:
    """``_probe_audio_duration`` darf nicht crashen wenn die Datei fehlt
    — returnt 0.0 als Sentinel."""
    from services.export_service import _probe_audio_duration

    bad = tmp_path / "does_not_exist.wav"
    result = _probe_audio_duration(str(bad))
    assert result == 0.0
