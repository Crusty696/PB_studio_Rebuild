from __future__ import annotations

import pytest


def test_b393_export_rejects_parent_directory_output_name_before_db(tmp_path, monkeypatch):
    from services import export_service as exp

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")

    class _SessionMustNotOpen:
        def __init__(self, *args, **kwargs):
            raise AssertionError("DB session opened before output_name validation")

    monkeypatch.setattr(exp, "Session", _SessionMustNotOpen)

    with pytest.raises(ValueError, match="output_name"):
        exp.export_timeline(project_id=1, output_name="..\\outside.mp4")

