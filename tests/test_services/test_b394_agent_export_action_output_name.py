from __future__ import annotations


class _SignalRecorder:
    def __init__(self):
        self.emits: list[tuple[str, dict]] = []

    def emit(self, action_name: str, payload: dict) -> None:
        self.emits.append((action_name, payload))


class _TaskManagerStub:
    def __init__(self):
        self.agent_command_signal = _SignalRecorder()


def test_b394_export_action_rejects_absolute_output_path(monkeypatch):
    from services.actions import edit_actions

    task_manager = _TaskManagerStub()
    monkeypatch.setattr(edit_actions, "_get_task_manager", lambda: task_manager)

    result = edit_actions.export_timeline_action(1, output_path=r"C:\Temp\x.mp4")

    assert "error" in result
    assert task_manager.agent_command_signal.emits == []


def test_b394_export_action_accepts_filename_only(monkeypatch):
    from services.actions import edit_actions

    task_manager = _TaskManagerStub()
    monkeypatch.setattr(edit_actions, "_get_task_manager", lambda: task_manager)

    result = edit_actions.export_timeline_action(1, output_path="safe_name.mp4")

    assert result["status"] == "Task in Warteschlange"
    assert task_manager.agent_command_signal.emits == [
        ("export_timeline", {"project_id": 1, "output_name": "safe_name.mp4"})
    ]
