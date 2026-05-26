from __future__ import annotations

import os
import time


def test_b400_cleanup_removes_old_concat_and_filtergraph_tempfiles(tmp_path, monkeypatch):
    from services import export_service as exp

    old_concat = tmp_path / "pb_concat_old.txt"
    old_fcs = tmp_path / "pb_fcs_old.txt"
    unrelated = tmp_path / "pb_other_old.txt"
    for path in (old_concat, old_fcs, unrelated):
        path.write_text("x", encoding="utf-8")
        old_ts = time.time() - 7200
        os.utime(path, (old_ts, old_ts))

    monkeypatch.setattr(exp.tempfile, "gettempdir", lambda: str(tmp_path))

    deleted = exp._cleanup_orphan_tempfiles(max_age_hours=1.0)

    assert deleted == 2
    assert not old_concat.exists()
    assert not old_fcs.exists()
    assert unrelated.exists()
