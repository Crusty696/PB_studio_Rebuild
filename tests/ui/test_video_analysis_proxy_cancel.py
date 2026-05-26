from types import SimpleNamespace

from ui.controllers import video_analysis


class _FakeTaskManager:
    def __init__(self, status: str):
        self.status = status
        self.finish_calls: list[tuple[str, str, str]] = []

    def get_task(self, task_id: str):
        return SimpleNamespace(status=self.status)

    def finish_task(self, task_id: str, status: str = "finished", message: str = ""):
        self.finish_calls.append((task_id, status, message))


def test_b362_proxy_finished_empty_does_not_override_cancelled_task(monkeypatch):
    manager = _FakeTaskManager(status="cancelled")
    monkeypatch.setattr(video_analysis, "_get_task_manager", lambda: manager)
    controller = object.__new__(video_analysis.VideoAnalysisController)

    controller._on_proxy_finished(clip_id=362, proxy_path="", title="clip", task_id="task-362")

    assert manager.finish_calls == []


def test_b362_proxy_finished_empty_still_errors_when_task_not_cancelled(monkeypatch):
    manager = _FakeTaskManager(status="running")
    monkeypatch.setattr(video_analysis, "_get_task_manager", lambda: manager)
    controller = object.__new__(video_analysis.VideoAnalysisController)

    controller._on_proxy_finished(clip_id=362, proxy_path="", title="clip", task_id="task-362")

    assert manager.finish_calls == [("task-362", "error", "Leerer Proxy-Pfad")]
