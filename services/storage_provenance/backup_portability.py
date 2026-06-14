from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile


BACKUP_VERSION = 1
STORAGE_LAYOUT_VERSION = 1
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class BackupSettings:
    backup_dir: Path
    frequency: str = "manual"

    def __post_init__(self) -> None:
        if self.frequency not in {"manual", "daily", "weekly"}:
            raise ValueError(f"Unsupported backup frequency: {self.frequency!r}")


@dataclass(frozen=True)
class StorageBackupResult:
    backup_path: Path
    storage_file_count: int
    db_bytes: int


@dataclass(frozen=True)
class StorageRestoreResult:
    project_root: Path
    storage_file_count: int


class StoragePortabilityBackupService:
    """Portable backup/restore for PB DB plus global by_sha storage."""

    def __init__(self, *, db_path: str | Path, storage_root: str | Path) -> None:
        self.db_path = Path(db_path)
        self.storage_root = Path(storage_root)

    def create_backup(
        self,
        backup_path: str | Path,
        *,
        model_versions: dict[str, str] | None = None,
        schema_version: str | None = None,
    ) -> StorageBackupResult:
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Database missing: {self.db_path}")
        output = Path(backup_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        storage_files = self._collect_by_sha_files()
        manifest = {
            "backup_version": BACKUP_VERSION,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "db_schema_version": schema_version or _sqlite_user_version(self.db_path),
            "storage_layout_version": STORAGE_LAYOUT_VERSION,
            "model_versions": model_versions or {},
            "database": {
                "path": "database/pb_studio.db",
                "bytes": self.db_path.stat().st_size,
            },
            "storage_files": [
                {
                    "path": f"storage/{relative.as_posix()}",
                    "bytes": source.stat().st_size,
                }
                for relative, source in storage_files
            ],
        }

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
            db_tmp = output.parent / f"{output.stem}.pb_studio.db.tmp"
            try:
                _sqlite_backup(self.db_path, db_tmp)
                zf.write(db_tmp, "database/pb_studio.db")
            finally:
                db_tmp.unlink(missing_ok=True)
            for relative, source in storage_files:
                zf.write(source, f"storage/{relative.as_posix()}")

        return StorageBackupResult(
            backup_path=output,
            storage_file_count=len(storage_files),
            db_bytes=self.db_path.stat().st_size,
        )

    def restore_backup(self, backup_path: str | Path, *, target_project_root: str | Path) -> StorageRestoreResult:
        target_root = Path(target_project_root)
        target_db = target_root / "database" / "pb_studio.db"
        target_storage = target_root / "storage"
        target_root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(backup_path) as zf:
            manifest = _load_manifest(zf)
            target_db.parent.mkdir(parents=True, exist_ok=True)
            target_db.write_bytes(zf.read(manifest["database"]["path"]))
            restored = 0
            for entry in manifest["storage_files"]:
                zip_name = entry["path"]
                relative = Path(zip_name).relative_to("storage")
                target = target_storage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(zip_name))
                restored += 1

        return StorageRestoreResult(project_root=target_root, storage_file_count=restored)

    def _collect_by_sha_files(self) -> list[tuple[Path, Path]]:
        by_sha = self.storage_root / "by_sha"
        if not by_sha.exists():
            return []
        files: list[tuple[Path, Path]] = []
        for source in sorted(path for path in by_sha.rglob("*") if path.is_file()):
            files.append((source.relative_to(self.storage_root), source))
        return files


def _load_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except KeyError as exc:
        raise ValueError("Backup missing manifest.json") from exc
    if manifest.get("backup_version") != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {manifest.get('backup_version')!r}")
    for key in ("db_schema_version", "storage_layout_version", "model_versions", "database", "storage_files"):
        if key not in manifest:
            raise ValueError(f"Backup manifest missing key: {key}")
    return manifest


def _sqlite_backup(src_db: Path, dst_db: Path) -> None:
    src = f"file:{src_db.as_posix()}?mode=ro"
    with sqlite3.connect(src, uri=True) as src_conn:
        with sqlite3.connect(dst_db) as dst_conn:
            src_conn.backup(dst_conn)


def _sqlite_user_version(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("PRAGMA user_version").fetchone()[0])


def copy_directory_following_links(source: str | Path, target: str | Path) -> None:
    """Full-copy directory contents; junction/symlink targets become real files."""

    src = Path(source)
    dst = Path(target)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=False)
