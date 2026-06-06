"""B-472: 'Video komplett analysieren' must not silently do nothing.

Click-log evidence (2026-06-04): 8 clicks on btn_video_pipeline produced zero
log/task/error lines because _start_video_pipeline returned silently when no
clips were checked/selected (and on a missing model). Fix: with no selection the
pipeline falls back to ALL project videos (as the tooltip promises and as the
'Video analysieren' button already behaves), with logging + visible feedback.

Source-level guard (repo idiom, like B-275/B-470). Live verification in the app
remains required before `fixed`.
"""

from __future__ import annotations

from pathlib import Path


def _pipeline_body() -> str:
    src = Path("ui/controllers/video_analysis.py").read_text(encoding="utf-8")
    return src.split("def _start_video_pipeline", 1)[1].split("\n    def ", 1)[0]


def test_no_selection_falls_back_to_all_videos():
    body = _pipeline_body()
    assert "get_all_video" in body, (
        "B-472: without a selection the pipeline must fall back to all project "
        "videos (get_all_video) instead of silently returning"
    )


def test_missing_model_is_logged_not_silent():
    body = _pipeline_body()
    assert "if not model: return" not in body, (
        "B-472: bare silent `if not model: return` must not come back"
    )
    assert "video_pool_table hat kein Model" in body


def test_pool_refresh_reevaluates_workflow_gates():
    """B-472 root #2: gates ran only on workspace switch; an async pool load
    after the gate pass left btn_video_pipeline permanently disabled."""
    src = Path("ui/controllers/media_table.py").read_text(encoding="utf-8")
    body = src.split("def _apply_refreshed_data", 1)[1].split("\n    def ", 1)[0]
    assert "_update_workflow_gates" in body, (
        "B-472: _apply_refreshed_data must re-evaluate workflow gates after a "
        "pool refresh, otherwise analysis buttons stay disabled forever"
    )


def test_empty_project_gives_visible_feedback():
    body = _pipeline_body()
    assert "status_bar.showMessage" in body, (
        "B-472: an empty project must produce visible feedback (statusbar), "
        "not only a console_text line"
    )
    assert body.count("logger.") >= 3, "B-472: abort/fallback paths must log"
