"""OTK-021 portable backup/restore verifier.

Creates a temporary WAL-mode SQLite DB plus real storage/by_sha files, runs the
real StoragePortabilityBackupService, restores into a second temporary project
root, and verifies DB contents, manifest, and file hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_DIR = REPO_ROOT / "tests" / "qa_artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA user_version=21")
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES ('wal-visible')")
        conn.commit()


def _read_db_value(db_path: Path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        return {
            "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
            "sample_value": conn.execute("SELECT value FROM sample WHERE id=1").fetchone()[0],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args()

    from services.storage_provenance.backup_portability import StoragePortabilityBackupService
    from services.storage_provenance.layout import StorageLayout

    work_dir = Path(tempfile.mkdtemp(prefix="pb-otk021-backup-restore-", dir=str(ARTIFACT_DIR)))
    db_path = work_dir / "source" / "database" / "pb_studio.db"
    storage_root = work_dir / "source" / "storage"
    restore_root = work_dir / "restored-project"
    backup_path = work_dir / "backup" / "pb-storage.zip"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage_root.mkdir(parents=True, exist_ok=True)
    _write_db(db_path)

    sha_a = "a" * 64
    sha_b = "b" * 64
    layout = StorageLayout(storage_root)
    file_a = layout.ensure_source_root(sha_a) / "audio" / "stem.wav"
    file_b = layout.ensure_source_root(sha_b) / "video" / "proxy.mp4"
    file_a.write_bytes(b"stem-data-" + bytes(range(16)))
    file_b.write_bytes(b"proxy-data-" + bytes(range(32)))
    expected_hashes = {
        "storage/by_sha/aa/" + sha_a + "/audio/stem.wav": _sha256(file_a),
        "storage/by_sha/bb/" + sha_b + "/video/proxy.mp4": _sha256(file_b),
    }

    result: dict[str, object] = {
        "ok": False,
        "work_dir": str(work_dir),
        "db_path": str(db_path),
        "storage_root": str(storage_root),
        "backup_path": str(backup_path),
        "restore_root": str(restore_root),
        "expected_hashes": expected_hashes,
    }

    try:
        service = StoragePortabilityBackupService(db_path=db_path, storage_root=storage_root)
        backup = service.create_backup(
            backup_path,
            model_versions={"demucs": "4.0.1", "siglip": "so400m"},
            schema_version="otk021-live",
        )
        restore = service.restore_backup(backup_path, target_project_root=restore_root)
        restored_db = restore.project_root / "database" / "pb_studio.db"
        restored_hashes = {
            f"storage/{p.relative_to(restore.project_root / 'storage').as_posix()}": _sha256(p)
            for p in sorted((restore.project_root / "storage").rglob("*"))
            if p.is_file()
        }
        db_value = _read_db_value(restored_db)
        with zipfile.ZipFile(backup_path) as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            zip_names = sorted(zf.namelist())
        result.update(
            {
                "backup_storage_file_count": backup.storage_file_count,
                "restore_storage_file_count": restore.storage_file_count,
                "backup_size_bytes": backup_path.stat().st_size,
                "restored_db": str(restored_db),
                "restored_db_value": db_value,
                "restored_hashes": restored_hashes,
                "manifest": manifest,
                "zip_names": zip_names,
            }
        )
        result["ok"] = (
            backup.storage_file_count == 2
            and restore.storage_file_count == 2
            and backup_path.is_file()
            and db_value == {"user_version": 21, "sample_value": "wal-visible"}
            and restored_hashes == expected_hashes
            and manifest["db_schema_version"] == "otk021-live"
            and manifest["storage_layout_version"] == 1
            and manifest["model_versions"] == {"demucs": "4.0.1", "siglip": "so400m"}
            and manifest["database"]["path"] == "database/pb_studio.db"
            and len(manifest["storage_files"]) == 2
        )
    except Exception as exc:  # noqa: BLE001 - verifier must report harness failure.
        result["error"] = f"{type(exc).__name__}: {exc}"

    result_path = ARTIFACT_DIR / "otk021_backup_restore_portable_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.keep_workdir and result.get("ok"):
        # Keep the JSON evidence, remove the bulky temp payload.
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
