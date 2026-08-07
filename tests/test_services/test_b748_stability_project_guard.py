"""B-748: live stability runs must never touch host projects."""

from pathlib import Path

import pytest

from services.project_manager import ProjectManager


@pytest.mark.parametrize("operation", ("create", "open", "save_as"))
def test_b748_blocks_host_project_before_any_project_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    allowed = tmp_path / "stability" / "project"
    host_project = tmp_path / "host-project"
    monkeypatch.setenv("PB_STABILITY_PROJECT", str(allowed))

    manager = ProjectManager()

    def _unexpected_wait(*_args, **_kwargs):
        raise AssertionError("task wait must not run before stability scope guard")

    monkeypatch.setattr(manager, "_wait_for_tasks_idle", _unexpected_wait)

    with pytest.raises(PermissionError, match="B-748"):
        if operation == "create":
            manager.create_project(host_project, "host")
        elif operation == "open":
            manager.open_project(host_project)
        else:
            manager.save_project_as(host_project)


def test_b748_allows_project_below_configured_stability_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stability_root = tmp_path / "stability-run"
    allowed_project = stability_root / "project" / "STAB-W3"
    allowed_project.mkdir(parents=True)
    monkeypatch.delenv("PB_STABILITY_PROJECT", raising=False)
    monkeypatch.setenv("PB_STABILITY_PROJECT_ROOT", str(stability_root))
    monkeypatch.setattr(
        ProjectManager,
        "_wait_for_tasks_idle",
        staticmethod(lambda *_args, **_kwargs: True),
    )

    with pytest.raises(FileNotFoundError, match="pb_studio.db"):
        ProjectManager().open_project(allowed_project)
