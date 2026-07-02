from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
VERSION = "0.5.0"
INSTALLER_EXE = DIST / f"pb_studio_setup_v{VERSION}.exe"
INSTALLER_PAYLOAD = DIST / f"pb_studio_setup_v{VERSION}.nsisbin"
CHECKSUMS = DIST / f"PB_Studio_v{VERSION}_SHA256SUMS.txt"
BUNDLE = DIST / f"PB_Studio_v{VERSION}_distribution.zip"
OUT = ROOT / "tests" / "qa_artifacts" / "distribution_bundle.json"

EXTRA_FILES = [
    ROOT / "LICENSE.txt",
    ROOT / "docs" / "user" / "INSTALLATION_GUIDE.md",
    ROOT / "docs" / "DEPLOYMENT.md",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _file_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256(path) if path.is_file() else None,
    }


def main() -> int:
    required = [INSTALLER_EXE, INSTALLER_PAYLOAD, *EXTRA_FILES]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing distribution input(s): " + ", ".join(missing))

    checksum_targets = [INSTALLER_EXE, INSTALLER_PAYLOAD]
    checksum_lines = [f"{_sha256(path)}  {path.name}" for path in checksum_targets]
    CHECKSUMS.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    entries: list[tuple[Path, str]] = [
        (INSTALLER_EXE, INSTALLER_EXE.name),
        (INSTALLER_PAYLOAD, INSTALLER_PAYLOAD.name),
        (CHECKSUMS, CHECKSUMS.name),
        (ROOT / "LICENSE.txt", "LICENSE.txt"),
        (ROOT / "docs" / "user" / "INSTALLATION_GUIDE.md", "INSTALLATION_GUIDE.md"),
        (ROOT / "docs" / "DEPLOYMENT.md", "DEPLOYMENT.md"),
    ]
    if BUNDLE.exists():
        BUNDLE.unlink()
    with ZipFile(BUNDLE, "w", compression=ZIP_STORED) as archive:
        for source, arcname in entries:
            archive.write(source, arcname)

    result = {
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": _file_record(BUNDLE),
        "checksums": _file_record(CHECKSUMS),
        "entries": [arcname for _, arcname in entries],
        "installer": _file_record(INSTALLER_EXE),
        "payload": _file_record(INSTALLER_PAYLOAD),
        "compression": "ZIP_STORED",
        "honest_limit": "Bundle creation packages existing artifacts only; release validity is still controlled by tools/release_gate.py.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
