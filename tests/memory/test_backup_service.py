from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from services.backup_service import (
    BackupService,
    BackupInfo,
    run_pre_migration_backup,
    run_startup_backup,
)


def _make_empty_sqlite(path: Path) -> None:
    """Create a minimal SQLite file for backup testing."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


def test_backup_creates_dated_file(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    result_path = svc.backup(reason="manual")
    assert result_path.exists()
    # File name must start with pb_studio_
    assert result_path.name.startswith("pb_studio_")
    # And the file must have meaningful content (the source DB)
    assert result_path.stat().st_size > 0

    # list_backups should include it
    backups = svc.list_backups()
    assert len(backups) == 1
    assert backups[0].path == result_path


def test_rolling_window_keeps_only_14(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    # Create 20 backups (bypass the datetime collision by inserting a tiny sleep
    # or by manually crafting filenames with a sequential timestamp)
    for i in range(20):
        # Different approach: directly seed the backup_dir with 20 differently
        # named files, then invoke prune.
        fake_path = backup_dir / f"pb_studio_2026-04-{(i % 28) + 1:02d}-{i:06d}.db"
        backup_dir.mkdir(parents=True, exist_ok=True)
        fake_path.write_bytes(b"fake")

    # Create one more REAL backup which calls prune internally
    svc.backup(reason="manual")
    remaining = svc.list_backups()
    # Must be at most ROLLING_WINDOW (14)
    assert len(remaining) == BackupService.ROLLING_WINDOW
    # The oldest (lowest timestamp) should have been deleted
    oldest_name = remaining[-1].path.name
    assert "2026-04-01" not in oldest_name  # first seeded file shouldn't survive


def test_daily_check_skips_if_last_within_24h(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    # First backup should happen
    first = svc.backup_if_stale(reason="daily")
    assert first is not None

    # Second, immediate call: no new backup (within 24h window)
    second = svc.backup_if_stale(reason="daily")
    assert second is None
    # Exactly one backup in the dir
    assert len(svc.list_backups()) == 1


def test_daily_check_creates_after_24h(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    # Manually seed an old backup file (name-timestamp > 24h ago)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime(
        "%Y-%m-%d-%H%M%S"
    )
    old_file = backup_dir / f"pb_studio_{old_ts}.db"
    backup_dir.mkdir(parents=True, exist_ok=True)
    old_file.write_bytes(b"fake")

    # Now backup_if_stale should create a new one
    new_path = svc.backup_if_stale(reason="daily")
    assert new_path is not None
    assert new_path != old_file


def test_daily_not_suppressed_by_recent_pre_migration_backup(tmp_path: Path) -> None:
    """B-527: Ein frischer pre-migration-Snapshot (erzeugt im selben Startlauf
    VOR dem daily-Backup) darf das taegliche Backup NICHT unterdruecken — sonst
    entsteht nie ein ``*_daily.db``.
    """
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    # Simuliert run_pre_migration_backup im selben Start (frisch, < 24h).
    pre = svc.backup(reason="pre-migration")
    assert pre.exists()

    # daily darf trotzdem erzeugt werden.
    daily = svc.backup_if_stale(reason="daily")
    assert daily is not None, "B-527: daily-Backup wurde durch pre-migration unterdrueckt"
    assert "_daily" in daily.name

    # Zweiter Start innerhalb 24h: daily existiert -> skip (Kadenz korrekt).
    again = svc.backup_if_stale(reason="daily")
    assert again is None


def test_destructive_action_hook_triggers_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    assert len(svc.list_backups()) == 0
    with svc.pattern_reset_context():
        # User would do destructive op here; we just verify timing:
        # by the time we're IN the context, a backup already exists.
        assert len(svc.list_backups()) == 1
    # After context: still exactly one (not two).
    assert len(svc.list_backups()) == 1


def test_list_backups_sorted_newest_first(tmp_path: Path) -> None:
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)

    # Seed files with known, distinct timestamps
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "pb_studio_2026-04-01-100000.db").write_bytes(b"a")
    (backup_dir / "pb_studio_2026-04-10-100000.db").write_bytes(b"b")
    (backup_dir / "pb_studio_2026-04-05-100000.db").write_bytes(b"c")

    backups = svc.list_backups()
    names = [b.path.name for b in backups]
    assert names == [
        "pb_studio_2026-04-10-100000.db",
        "pb_studio_2026-04-05-100000.db",
        "pb_studio_2026-04-01-100000.db",
    ]


def test_missing_db_raises(tmp_path: Path) -> None:
    svc = BackupService(
        db_path=tmp_path / "does_not_exist.db", backup_dir=tmp_path / "backups"
    )
    with pytest.raises(FileNotFoundError):
        svc.backup()


def test_malformed_filename_is_ignored(tmp_path: Path) -> None:
    """Stray files in backup_dir must not crash list_backups()."""
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "pb_studio_2026-04-10-100000.db").write_bytes(b"a")
    (backup_dir / "random_file.txt").write_bytes(b"noise")
    (backup_dir / "pb_studio_not_a_date.db").write_bytes(b"bad")

    svc = BackupService(db_path=db_path, backup_dir=backup_dir)
    backups = svc.list_backups()
    # Only the one well-formed file
    assert len(backups) == 1
    assert backups[0].path.name == "pb_studio_2026-04-10-100000.db"


# ── B-498: WAL-Sicherheit + Auto-Backup-Einstiegspunkte ────────────────────


def test_backup_wal_db_contains_uncheckpointed_commit(tmp_path: Path) -> None:
    """B-498: Letzter Commit liegt nur im -wal-Sidecar (kein Checkpoint).

    Ein naiver Datei-Copy (shutil.copy2, alter Code) wuerde diesen Commit
    verlieren — die sqlite3.Connection.backup()-API muss ihn enthalten.
    """
    db_path = tmp_path / "db.db"
    writer = sqlite3.connect(str(db_path))
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE t (x INTEGER)")
        writer.execute("INSERT INTO t VALUES (42)")
        writer.commit()
        # Kein Checkpoint, Writer-Connection bleibt offen → Daten leben im WAL.
        wal_file = tmp_path / "db.db-wal"
        assert wal_file.exists() and wal_file.stat().st_size > 0

        svc = BackupService(db_path=db_path, backup_dir=tmp_path / "backups")
        backup_path = svc.backup(reason="waltest")
    finally:
        writer.close()

    out = sqlite3.connect(str(backup_path))
    try:
        rows = out.execute("SELECT x FROM t").fetchall()
    finally:
        out.close()
    assert rows == [(42,)]


def test_pre_migration_backup_creates_listed_file(tmp_path: Path) -> None:
    """B-498: reason='pre-migration' erzeugt eine Datei, die list_backups()
    auch sieht (Filename-Regex muss '-' im Reason erlauben)."""
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)

    result = run_pre_migration_backup(
        db_path=db_path, backup_dir=tmp_path / "backups"
    )
    assert result is not None
    assert result.exists()
    assert result.name.endswith("_pre-migration.db")

    svc = BackupService(db_path=db_path, backup_dir=tmp_path / "backups")
    infos = svc.list_backups()
    assert len(infos) == 1
    assert infos[0].reason == "pre-migration"


def test_run_startup_backup_never_raises(tmp_path: Path) -> None:
    """B-498: Backup-Fehler duerfen den Aufrufer (App-Start) nicht crashen."""
    # (a) DB existiert nicht → FileNotFoundError intern → None, kein Raise.
    result = run_startup_backup(
        db_path=tmp_path / "missing.db", backup_dir=tmp_path / "backups"
    )
    assert result is None

    # (b) Beliebige Exception im Backup-Pfad → None, kein Raise.
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    with patch.object(
        BackupService, "backup_if_stale", side_effect=RuntimeError("boom")
    ):
        result = run_startup_backup(
            db_path=db_path, backup_dir=tmp_path / "backups"
        )
    assert result is None


def test_run_startup_backup_creates_file_on_happy_path(tmp_path: Path) -> None:
    """B-498: Happy-Path des Startup-Hooks erzeugt eine daily-Datei."""
    db_path = tmp_path / "db.db"
    _make_empty_sqlite(db_path)
    result = run_startup_backup(
        db_path=db_path, backup_dir=tmp_path / "backups", reason="daily"
    )
    assert result is not None
    assert result.exists()
    assert result.name.endswith("_daily.db")


def test_run_pre_migration_backup_never_raises(tmp_path: Path) -> None:
    """B-498: Pre-Migration-Backup-Fehler crasht die Migration nicht."""
    with patch.object(BackupService, "backup", side_effect=RuntimeError("boom")):
        result = run_pre_migration_backup(
            db_path=tmp_path / "x.db", backup_dir=tmp_path / "backups"
        )
    assert result is None


def test_no_deprecated_utcnow_usage() -> None:
    source = Path("services/backup_service.py").read_text(encoding="utf-8")
    assert (
        "datetime.utcnow(" not in source
    ), "deprecated datetime.utcnow() usage detected"
