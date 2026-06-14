from __future__ import annotations

import json
import sqlite3
import zipfile

import pytest

from services.storage_provenance.backup_portability import (
    BackupSettings,
    StoragePortabilityBackupService,
)


def test_storage_backup_and_restore_roundtrip(tmp_path, mock_project_with_artifacts) -> None:
    db_path = tmp_path / "pb_studio.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version=7")
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('ok')")

    backup_path = tmp_path / "backup" / "pb-storage.zip"
    service = StoragePortabilityBackupService(
        db_path=db_path,
        storage_root=mock_project_with_artifacts["storage_root"],
    )

    result = service.create_backup(
        backup_path,
        model_versions={"demucs": "4.0.1"},
    )
    restore = service.restore_backup(backup_path, target_project_root=tmp_path / "restore")

    restored_db = restore.project_root / "database" / "pb_studio.db"
    restored_artifact = restore.project_root / "storage" / "by_sha" / mock_project_with_artifacts["source_sha"][:2] / mock_project_with_artifacts["source_sha"] / "video" / "proxy.mp4"

    assert result.storage_file_count == 1
    assert restore.storage_file_count == 1
    assert restored_artifact.read_bytes() == b"proxy"
    with sqlite3.connect(restored_db) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "ok"
    with zipfile.ZipFile(backup_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["db_schema_version"] == "7"
    assert manifest["storage_layout_version"] == 1
    assert manifest["model_versions"] == {"demucs": "4.0.1"}


def test_backup_settings_accepts_only_known_frequency(tmp_path) -> None:
    assert BackupSettings(tmp_path, "manual").frequency == "manual"
    assert BackupSettings(tmp_path, "daily").frequency == "daily"
    assert BackupSettings(tmp_path, "weekly").frequency == "weekly"
    with pytest.raises(ValueError, match="Unsupported backup frequency"):
        BackupSettings(tmp_path, "hourly")
