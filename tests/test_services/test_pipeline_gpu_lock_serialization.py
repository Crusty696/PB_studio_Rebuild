"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T2.3: GPU-Lock-Serialisierung - kein Race zwischen Stages oder Cross-Pipeline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import threading
import time
import pytest


def test_two_stages_serialize_via_gpu_lock():
    """Plan A-3 + AC-8: zwei GPU-Stages parallel -> seriellisiert via GPU_EXECUTION_LOCK."""
    from services.audio_pipeline.stages import StemGenStage, BeatGridStage
    from services.audio_pipeline.context import PipelineContext
    from services.model_manager import GPU_EXECUTION_LOCK

    timeline = []
    lock_acquired_at = []

    def make_slow_stem_mock(label):
        m = MagicMock()
        def slow_separate(*a, **kw):
            timeline.append(f"{label}_start")
            time.sleep(0.15)
            timeline.append(f"{label}_done")
            return {"drums": "/p", "bass": "/p", "vocals": "/p", "other": "/p"}
        m.return_value.separate_to.side_effect = slow_separate
        return m

    def make_slow_beat_mock(label):
        m = MagicMock()
        def slow_beat(*a, **kw):
            timeline.append(f"{label}_start")
            time.sleep(0.15)
            timeline.append(f"{label}_done")
            return {"bpm": 128}
        m.return_value.analyze_and_store.side_effect = slow_beat
        return m

    ctx1 = PipelineContext(track_id=1, original_path="/a.wav")
    ctx2 = PipelineContext(track_id=2, original_path="/b.wav")

    # Bypass DB-Write via mock
    with patch("services.audio_pipeline.stages.nullpool_session", None):
        s1 = StemGenStage(separator_cls=make_slow_stem_mock("stem"))
        s2 = BeatGridStage(service_cls=make_slow_beat_mock("beat"))

        t1 = threading.Thread(target=lambda: s1.run(ctx1))
        t2 = threading.Thread(target=lambda: s2.run(ctx2))
        t1.start()
        time.sleep(0.02)  # damit t1 zuerst startet
        t2.start()
        t1.join()
        t2.join()

    # Eine Stage muss komplett vor Start der anderen abgeschlossen sein.
    # Zulaessig: ["stem_start","stem_done","beat_start","beat_done"] (oder umgekehrt).
    # NICHT zulaessig: interleaved (z.B. stem_start, beat_start, stem_done, beat_done).
    # Pruefe: Index von stem_done < Index von beat_start ODER umgekehrt.
    sd = timeline.index("stem_done")
    bs = timeline.index("beat_start")
    bd = timeline.index("beat_done")
    ss = timeline.index("stem_start")
    serialized = (sd < bs) or (bd < ss)
    assert serialized, f"GPU-Lock-Race - timeline: {timeline}"


def test_stem_gen_stage_releases_lock_so_external_holder_can_proceed():
    """fixt R-06: nach StemGenStage-Release koennen andere GPU-Holder fortfahren."""
    from services.audio_pipeline.stages import StemGenStage
    from services.audio_pipeline.context import PipelineContext
    from services.model_manager import GPU_EXECUTION_LOCK

    external_acquired = threading.Event()

    def external_worker():
        with GPU_EXECUTION_LOCK:
            external_acquired.set()

    mock_sep = MagicMock()
    mock_sep.return_value.separate_to.return_value = {
        "drums": "/p", "bass": "/p", "vocals": "/p", "other": "/p"
    }

    ctx = PipelineContext(track_id=1, original_path="/a.wav")
    with patch("services.audio_pipeline.stages.nullpool_session", None):
        s = StemGenStage(separator_cls=mock_sep)
        s.run(ctx)

    # Nach Stage-Done muss externer Worker den Lock holen koennen.
    t = threading.Thread(target=external_worker)
    t.start()
    t.join(timeout=1.0)
    assert external_acquired.is_set(), "External-Holder konnte Lock nicht holen -> Release-Bug"
