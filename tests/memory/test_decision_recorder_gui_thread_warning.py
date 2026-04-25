"""B-104 / BUG-3-b regression test:

``DecisionRecorder.record()`` can block up to ~2.1s on SQLite contention
(3 retries × cumulative backoff). When called on the Qt GUI thread that
becomes a UI freeze of N × 2.1s for an N-cut run.

The fix logs a warning the first time ``record()`` runs on the GUI
thread. Tests/CLI without QApplication are silently allowed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from services.pacing.decision_recorder import DecisionRecorder
from services.pacing.scorer import AudioContext, ClipFeatures
from tests.memory.test_decision_recorder import (
    _build_sqlite_with_mem_decision as _build_sqlite,
    _seed_run,
    _make_ctx,
    _make_clip,
)


def _make_ctx_and_clip() -> tuple[AudioContext, ClipFeatures]:
    return _make_ctx(), _make_clip()


def test_record_on_main_thread_without_qapp_does_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests/CLI run on the main thread without a QApplication. The
    recorder must not warn in that case."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)
    ctx, clip = _make_ctx_and_clip()

    with caplog.at_level(logging.WARNING, logger="services.pacing.decision_recorder"):
        recorder.record(
            run_id=run_id, sequence_idx=0, ctx=ctx, chosen=clip,
            rationale={"chosen_score": 0.8}, agent_score=0.8,
        )

    assert "GUI thread" not in caplog.text, (
        f"Recorder should not warn when no QApplication is alive. "
        f"caplog: {caplog.text}"
    )


def test_record_on_qapp_main_thread_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When a QApplication exists and we're on its main thread, the
    recorder must emit a warning so wiring bugs surface in dev/test."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)
    ctx, clip = _make_ctx_and_clip()

    with caplog.at_level(logging.WARNING, logger="services.pacing.decision_recorder"):
        recorder.record(
            run_id=run_id, sequence_idx=0, ctx=ctx, chosen=clip,
            rationale={"chosen_score": 0.8}, agent_score=0.8,
        )

    assert "GUI thread" in caplog.text, (
        f"BUG-3-b regression: expected GUI-thread warning when QApplication "
        f"is running. caplog: {caplog.text}"
    )


def test_warning_only_logged_once_per_recorder(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Once-per-recorder noise gate. Repeat record() calls must not
    spam the log."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)
    ctx, clip = _make_ctx_and_clip()

    with caplog.at_level(logging.WARNING, logger="services.pacing.decision_recorder"):
        for seq in range(3):
            recorder.record(
                run_id=run_id, sequence_idx=seq, ctx=ctx, chosen=clip,
                rationale={"chosen_score": 0.8}, agent_score=0.8,
            )

    gui_warnings = [
        r for r in caplog.records if "GUI thread" in r.getMessage()
    ]
    assert len(gui_warnings) == 1, (
        f"Expected 1 GUI-thread warning, got {len(gui_warnings)}. "
        f"Noise-gate broken."
    )
