"""Tests fuer B-287 + B-289 — Pipeline-Worker markiert metadata_extract
und emittiert 100% vor finished."""
from __future__ import annotations

import inspect
from workers.video import VideoAnalysisPipelineWorker


def test_b287_pipeline_worker_marks_metadata_extract():
    """B-287-Regression: Pipeline-Worker.run muss metadata_extract markieren.

    Source-Inspection — Worker-Source enthaelt mark_done-Call mit step
    'metadata_extract' BEVOR run_full_pipeline aufgerufen wird (sonst
    bleibt Status bei 8/9 = 88%).
    """
    src = inspect.getsource(VideoAnalysisPipelineWorker.run)
    assert '"metadata_extract"' in src, (
        "B-287: VideoAnalysisPipelineWorker.run referenziert "
        '"metadata_extract" als Call-Argument nicht — Step bleibt unmarkiert.'
    )
    # Find the actual call-site (quoted), not the comment.
    pos_metadata = src.find('"metadata_extract"')
    pos_run_pipeline = src.find("run_full_pipeline(")
    assert pos_metadata < pos_run_pipeline, (
        "B-287: metadata_extract muss VOR run_full_pipeline gemarkt werden "
        f"(metadata at {pos_metadata}, run_full_pipeline at {pos_run_pipeline})."
    )


def test_b289_pipeline_worker_emits_100_before_finished():
    """B-289-Regression: vor finished.emit muss progress.emit(100, ...) stehen."""
    src = inspect.getsource(VideoAnalysisPipelineWorker.run)
    finished_idx = src.find("self.finished.emit(last_clip_id, {")
    assert finished_idx > 0, "finished.emit nicht gefunden — Layout veraendert?"
    window = src[max(0, finished_idx - 250):finished_idx]
    assert "progress.emit(100" in window, (
        "B-289: kein progress.emit(100, ...) in den 250 Zeichen vor "
        "finished.emit — UI bleibt bei 99%."
    )
