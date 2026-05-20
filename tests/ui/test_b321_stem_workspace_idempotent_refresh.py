from __future__ import annotations

from pathlib import Path


def test_stem_workspace_does_not_restart_peak_workers_for_same_track(qapp, monkeypatch, tmp_path: Path) -> None:
    from ui.widgets.stem_workspace import StemWorkspace

    paths = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = tmp_path / f"{name}.wav"
        path.write_bytes(b"fake")
        paths[name] = str(path)

    workspace = StemWorkspace()
    started: list[tuple[str, str]] = []
    monkeypatch.setattr(
        workspace,
        "_start_peak_generation",
        lambda stem_name, file_path: started.append((stem_name, file_path)),
    )

    try:
        workspace.update_for_track(2, paths)
        workspace.update_for_track(2, dict(paths))
    finally:
        workspace.deleteLater()

    assert started == [(name, paths[name]) for name in ("vocals", "drums", "bass", "other")]
