import os
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]


def test_b321_completion_bridge_uses_debounced_media_refresh():
    source = (ROOT / "ui" / "controllers" / "panel_setup.py").read_text(encoding="utf-8")

    assert "def setup_analysis_completion_bridge" in source
    bridge_body = source.split("def setup_analysis_completion_bridge", 1)[1].split(
        "def _console_append", 1
    )[0]

    assert "_refresh_media_table_debounced()" in bridge_body
    assert "media_table_controller._refresh_media_table()" not in bridge_body
    assert '"no table refresh"' in bridge_body


def test_b564_completion_bridge_refreshes_active_status_panel():
    source = (ROOT / "ui" / "controllers" / "panel_setup.py").read_text(encoding="utf-8")
    bridge_body = source.split("def setup_analysis_completion_bridge", 1)[1].split(
        "def _console_append", 1
    )[0]

    assert "_refresh_active_analysis_status_panel" in source
    assert "_refresh_active_analysis_status_panel(self.window, media_type, media_id)" in bridge_body
    assert 'getattr(panel, "_media_type", None) != media_type' in source
    assert 'getattr(panel, "_media_id", None) != media_id' in source
    assert "panel.refresh()" in source


def test_b564_refresh_active_analysis_status_panel_matches_selected_media():
    from ui.controllers.panel_setup import _refresh_active_analysis_status_panel

    class Panel:
        _media_type = "video"
        _media_id = 42

        def __init__(self):
            self.refresh_count = 0

        def refresh(self):
            self.refresh_count += 1

    panel = Panel()
    window = SimpleNamespace(_media_ws=SimpleNamespace(video_analysis_panel=panel))

    _refresh_active_analysis_status_panel(window, "video", 42)
    _refresh_active_analysis_status_panel(window, "video", 43)
    _refresh_active_analysis_status_panel(window, "audio", 42)

    assert panel.refresh_count == 1


def test_b321_completion_bridge_skips_video_intermediate_steps():
    from ui.controllers.panel_setup import _completion_should_refresh_media_table

    assert _completion_should_refresh_media_table("video", "metadata_extract") is True
    assert _completion_should_refresh_media_table("video", "scene_db_storage") is True

    for step in [
        "scene_detection",
        "motion_scores",
        "keyframe_extraction",
        "siglip_embeddings",
        "vector_db_storage",
        "ai_scene_caption",
    ]:
        assert _completion_should_refresh_media_table("video", step) is False

    assert _completion_should_refresh_media_table("audio", "bpm") is True
    assert _completion_should_refresh_media_table("unknown", "scene_db_storage") is False


def test_b321_project_dashboard_completion_refresh_is_debounced():
    dashboard_source = (
        ROOT / "ui" / "workspaces" / "workflow_pages.py"
    ).read_text(encoding="utf-8")
    setup_source = (
        ROOT / "ui" / "controllers" / "workspace_setup.py"
    ).read_text(encoding="utf-8")

    assert "refresh_requested = Signal()" in dashboard_source
    assert "self._refresh_debounce_timer = QTimer(self)" in dashboard_source
    assert "self._refresh_debounce_timer.setSingleShot(True)" in dashboard_source
    assert "self._refresh_debounce_timer.timeout.connect(self._refresh_current_project)" in dashboard_source
    assert "def request_refresh_debounced(self)" in dashboard_source
    assert "self._refresh_debounce_timer.start()" in dashboard_source
    assert "self.refresh_requested.connect(\n            self.request_refresh_debounced" in dashboard_source

    assert "self.window._project_dashboard.refresh_requested.emit()" in setup_source


def test_b321_project_dashboard_burst_refresh_requests_coalesce_to_one_call():
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from ui.workspaces.workflow_pages import ProjectDashboard

    app = QApplication.instance() or QApplication([])
    dashboard = ProjectDashboard()
    calls: list[int | None] = []

    def fake_refresh(project_id: int | None) -> None:
        calls.append(project_id)

    dashboard.refresh = fake_refresh  # type: ignore[method-assign]
    try:
        for _ in range(5):
            dashboard.refresh_requested.emit()

        loop = QEventLoop()
        QTimer.singleShot(900, loop.quit)
        loop.exec()
        app.processEvents()

        assert calls == [None]
    finally:
        dashboard.deleteLater()
