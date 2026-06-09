from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_project_dashboard_exposes_guided_cockpit_api():
    source = (ROOT / "ui" / "workspaces" / "workflow_pages.py").read_text(encoding="utf-8")

    assert "class ProjectDashboard" in source
    assert "action_requested = Signal(str)" in source
    assert "def refresh(self, project_id" in source
    assert "Qt.ConnectionType.QueuedConnection" in source
    assert "def _refresh_current_project" in source
    assert "self.readiness_cards" in source
    assert "self.warning_labels" in source
    assert "get_cockpit_readiness" in source


def test_workspace_setup_wires_cockpit_actions_and_completion_refresh():
    source = (ROOT / "ui" / "controllers" / "workspace_setup.py").read_text(encoding="utf-8")

    assert "action_requested.connect(self._handle_cockpit_action)" in source
    assert "def _handle_cockpit_action" in source
    assert "run_audio_complete" in source
    assert "run_video_pipeline" in source
    assert "register_completion_listener" in source
    assert "unregister_completion_listener" in source


def test_b343_completion_listeners_unregister_on_window_teardown():
    workspace_setup = (ROOT / "ui" / "controllers" / "workspace_setup.py").read_text(
        encoding="utf-8"
    )
    panel_setup = (ROOT / "ui" / "controllers" / "panel_setup.py").read_text(
        encoding="utf-8"
    )

    assert "self.window._cockpit_completion_listener" in workspace_setup
    assert "register_completion_listener(\n            self.window._cockpit_completion_listener" in workspace_setup
    assert "self.window.destroyed.connect(\n            lambda *_args: self._unregister_cockpit_listener()" in workspace_setup
    assert "def _unregister_cockpit_listener(self):" in workspace_setup
    assert "analysis_status_service.unregister_completion_listener(listener)" in workspace_setup

    assert "self.window._completion_bridge_listener = _bg_listener" in panel_setup
    assert "self.window.destroyed.connect(_unregister_bridge_listener)" in panel_setup
    assert "analysis_status_service.unregister_completion_listener(_bg_listener)" in panel_setup


def test_cockpit_primary_labels_are_user_facing_not_model_names():
    source = (ROOT / "ui" / "workspaces" / "workflow_pages.py").read_text(encoding="utf-8")

    primary_labels = [
        "Projekt starten",
        "Material importieren",
        "Audio analysieren",
        "Video analysieren",
        "Auto-Schnitt starten",
        "Timeline pruefen",
        "Export vorbereiten",
    ]
    for label in primary_labels:
        assert label in source
    assert "SigLIP analysieren" not in source
    assert "RAFT analysieren" not in source
