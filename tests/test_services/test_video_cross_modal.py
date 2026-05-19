"""Phase 39 — Cross-Modal-Alignment Tests.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_heuristic_no_beats_returns_empty():
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService,
    )
    svc = CrossModalAlignmentService()
    scenes = [{"index": 0, "start_s": 0.0, "end_s": 4.0},
              {"index": 1, "start_s": 4.0, "end_s": 8.0}]
    suggestions = svc.align(scenes=scenes, beats=[])
    assert suggestions == []


def test_heuristic_snaps_to_close_beat():
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService,
    )
    svc = CrossModalAlignmentService(snap_window_s=0.25)
    scenes = [
        {"index": 0, "start_s": 0.0, "end_s": 4.0},
        {"index": 1, "start_s": 4.0, "end_s": 8.0},
    ]
    beats = [0.5, 1.0, 2.0, 3.0, 4.05, 5.0]  # beat 4.05 nahe scene-boundary 4.0
    suggestions = svc.align(scenes=scenes, beats=beats)
    assert len(suggestions) == 1
    assert suggestions[0].time_s == 4.05
    assert suggestions[0].scene_idx == 1
    assert suggestions[0].confidence > 0.5


def test_heuristic_no_close_beat_no_suggestion():
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService,
    )
    svc = CrossModalAlignmentService(snap_window_s=0.1)
    scenes = [
        {"index": 0, "start_s": 0.0, "end_s": 4.0},
        {"index": 1, "start_s": 4.0, "end_s": 8.0},
    ]
    beats = [0.5, 2.0, 3.0, 5.0]   # nichts in der Naehe von 4.0
    suggestions = svc.align(scenes=scenes, beats=beats)
    assert suggestions == []


def test_drop_adds_confidence():
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService,
    )
    svc = CrossModalAlignmentService(snap_window_s=0.5)
    scenes = [
        {"index": 0, "start_s": 0.0, "end_s": 4.0},
        {"index": 1, "start_s": 4.0, "end_s": 8.0},
    ]
    beats = [4.2]  # dist=0.2, conf=0.6
    suggestions_no_drop = svc.align(scenes=scenes, beats=beats)
    suggestions_drop = svc.align(scenes=scenes, beats=beats, drops=[4.3])
    assert suggestions_drop[0].confidence > suggestions_no_drop[0].confidence


def test_reasoner_override(tmp_path: Path):
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService, ReasonerProtocol,
    )

    class _FakeReasoner:
        def reason_cut_plan(self, payload):
            return [{"time_s": 99.0, "confidence": 0.9, "reason": "ai-magic"}]

    svc = CrossModalAlignmentService(reasoner=_FakeReasoner())
    scenes = [{"index": 0, "start_s": 0.0, "end_s": 4.0},
              {"index": 1, "start_s": 4.0, "end_s": 8.0}]
    beats = [4.05]
    suggestions = svc.align(scenes=scenes, beats=beats)
    assert len(suggestions) == 1
    assert suggestions[0].time_s == 99.0
    assert suggestions[0].reason == "ai-magic"


def test_reasoner_failure_falls_back_to_heuristic():
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService,
    )

    class _BrokenReasoner:
        def reason_cut_plan(self, payload):
            raise RuntimeError("boom")

    svc = CrossModalAlignmentService(reasoner=_BrokenReasoner())
    scenes = [{"index": 0, "start_s": 0.0, "end_s": 4.0},
              {"index": 1, "start_s": 4.0, "end_s": 8.0}]
    beats = [4.05]
    # Trotzdem Suggestion vom Heuristik-Pfad
    suggestions = svc.align(scenes=scenes, beats=beats)
    assert len(suggestions) == 1
    assert suggestions[0].time_s == 4.05


def test_save_plan_to_json(tmp_path: Path):
    from services.video_pipeline.stages.cross_modal_alignment import (
        CrossModalAlignmentService, CutSuggestion,
    )
    svc = CrossModalAlignmentService()
    suggestions = [
        CutSuggestion(time_s=4.0, confidence=0.9, reason="test", scene_idx=1, beat_idx=2),
    ]
    target = tmp_path / "plan.json"
    svc.save_plan(suggestions, target)
    data = json.loads(target.read_text())
    assert data[0]["time_s"] == 4.0
    assert data[0]["scene_idx"] == 1
