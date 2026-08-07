"""B-743: Windows settings writes must honor the process APPDATA root."""

from __future__ import annotations

import json
from pathlib import Path

import services.settings_store as settings_store
from services.recent_projects import RecentProjectsManager


def test_settings_and_recent_projects_stay_inside_appdata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    host_home = tmp_path / "host-user"
    host_settings = (
        host_home / "AppData" / "Roaming" / "PBStudio" / "settings.json"
    )
    host_settings.parent.mkdir(parents=True)
    host_payload = {"recentProjects": ["host-project"]}
    host_settings.write_text(json.dumps(host_payload), encoding="utf-8")

    isolated_roaming = tmp_path / "isolated" / "AppData" / "Roaming"
    isolated_settings = isolated_roaming / "PBStudio" / "settings.json"
    isolated_settings.parent.mkdir(parents=True)
    isolated_settings.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(isolated_roaming))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: host_home))
    monkeypatch.setattr(settings_store, "_store", None)

    isolated_project = tmp_path / "isolated-project"
    isolated_project.mkdir()
    RecentProjectsManager.add(isolated_project)

    assert settings_store.get_settings_store()._path == isolated_settings
    assert json.loads(isolated_settings.read_text(encoding="utf-8")) == {
        "recentProjects": [str(isolated_project.resolve())]
    }
    assert json.loads(host_settings.read_text(encoding="utf-8")) == host_payload
