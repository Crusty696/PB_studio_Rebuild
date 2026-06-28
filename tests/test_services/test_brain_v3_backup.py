"""Tests fuer Brain V3 Backup-Service (Phase 6)."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta

import pytest

from services.brain.storage.backup import (
    BackupResult,
    backup_brain_v3_store,
    prune_old_backups,
    run_weekly_backup_if_due,
)
from services.brain.storage.brain_store import BrainStore


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def test_backup_creates_files_for_existing_dbs(isolated_appdata):
    BrainStore()  # init weights + patterns
    res = backup_brain_v3_store()
    assert isinstance(res, BackupResult)
    assert res.backup_dir.exists()
    assert any(p.name == "weights.db" for p in res.files_written)
    assert any(p.name == "patterns.db" for p in res.files_written)
    # Backup-Datei muss eine valide SQLite-DB sein
    import sqlite3
    weights_backup = res.backup_dir / "weights.db"
    conn = sqlite3.connect(str(weights_backup))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='axis_weights'"
        ).fetchall()
        assert rows, "axis_weights-Tabelle muss im Backup vorhanden sein"
    finally:
        conn.close()


def test_backup_skips_missing_dbs(isolated_appdata):
    # Kein BrainStore() → DBs existieren nicht
    res = backup_brain_v3_store()
    assert res.files_written == []
    assert len(res.skipped) >= 2


def test_backup_uses_custom_dir(isolated_appdata, tmp_path):
    BrainStore()
    custom = tmp_path / "my_backups"
    res = backup_brain_v3_store(backup_dir=custom)
    assert custom in res.backup_dir.parents


def test_prune_keeps_only_n(isolated_appdata, tmp_path):
    custom = tmp_path / "backups"
    custom.mkdir()
    # 6 fake-Backup-Subdirs mit verschiedenen timestamps
    for i in range(6):
        (custom / f"brain_v3_backup_2026010{i}_120000").mkdir()
    deleted = prune_old_backups(custom, keep=4)
    remaining = sorted([p.name for p in custom.iterdir() if p.is_dir()])
    assert len(remaining) == 4
    assert len(deleted) == 2
    # die 4 neuesten (hoechste timestamps) sind erhalten
    assert "brain_v3_backup_20260105_120000" in remaining
    assert "brain_v3_backup_20260100_120000" not in remaining


def test_prune_no_op_when_dir_missing(isolated_appdata, tmp_path):
    deleted = prune_old_backups(tmp_path / "does_not_exist", keep=4)
    assert deleted == []


def test_weekly_backup_runs_without_marker(isolated_appdata, tmp_path):
    BrainStore()
    state_file = tmp_path / "last_backup.txt"
    res = run_weekly_backup_if_due(
        state_file=state_file,
        backup_dir=tmp_path / "backups",
        now=datetime(2026, 5, 7, 12, 0, 0),
    )

    assert res.ran is True
    assert res.backup is not None
    assert state_file.exists()
    assert "2026-05-07T12:00:00" in state_file.read_text(encoding="utf-8")


def test_weekly_backup_skips_when_recent(isolated_appdata, tmp_path):
    BrainStore()
    state_file = tmp_path / "last_backup.txt"
    state_file.write_text("2026-05-06T12:00:00", encoding="utf-8")

    res = run_weekly_backup_if_due(
        state_file=state_file,
        backup_dir=tmp_path / "backups",
        now=datetime(2026, 5, 7, 12, 0, 0),
    )

    assert res.ran is False
    assert res.reason == "not_due"
    assert list((tmp_path / "backups").glob("brain_v3_backup_*")) == []


def test_weekly_backup_runs_when_marker_older_than_interval(isolated_appdata, tmp_path):
    BrainStore()
    state_file = tmp_path / "last_backup.txt"
    now = datetime(2026, 5, 7, 12, 0, 0)
    state_file.write_text((now - timedelta(days=8)).isoformat(), encoding="utf-8")

    res = run_weekly_backup_if_due(
        state_file=state_file,
        backup_dir=tmp_path / "backups",
        now=now,
        interval_days=7,
    )

    assert res.ran is True
    assert res.backup is not None
    assert "2026-05-07T12:00:00" in state_file.read_text(encoding="utf-8")


def test_pbwindow_boot_wires_weekly_backup_check():
    src = Path("main.py").read_text(encoding="utf-8")
    assert "_start_brain_v3_backup_check" in src
    assert "run_weekly_backup_if_due" in src
