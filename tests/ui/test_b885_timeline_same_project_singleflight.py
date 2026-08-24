"""B-885: identische Timeline-DB-Loads muessen single-flight bleiben."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("requested_project_id", [7, None])
def test_same_project_inflight_load_coalesces_before_teardown(
    monkeypatch, requested_project_id
):
    import database
    import shiboken6
    from ui.timeline import InteractiveTimeline

    monkeypatch.setattr(database, "get_active_project_id", lambda: 7)
    monkeypatch.setattr(shiboken6, "isValid", lambda obj: True)

    cancel_calls: list[bool] = []
    timeline = SimpleNamespace(
        _db_thread=SimpleNamespace(isRunning=lambda: True),
        _db_load_project_id=7,
        _cancel_pending_db_load=lambda: cancel_calls.append(True),
    )

    InteractiveTimeline.load_from_db(timeline, requested_project_id)

    assert cancel_calls == []
