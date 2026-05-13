"""Phase 1 live-smoke import helper.

Usage:
    python scripts/phase1_import_test.py --project-dir test_projects/Phase1_Live_Smoke_2 --import-dir test_import_phase1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from services.ingest_service import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, ingest_audio, ingest_video  # noqa: E402


def _resolve_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def run_import(project_dir: Path, import_dir: Path) -> int:
    if not import_dir.is_dir():
        print(f"FEHLER: Import-Ordner nicht gefunden: {import_dir}")
        return 2

    project_dir.mkdir(parents=True, exist_ok=True)
    database.set_project(project_dir)
    print(f"Importiere in Projekt: {project_dir}")

    files = sorted(import_dir.glob("*.*"))
    if not files:
        print(f"FEHLER: Import-Ordner enthaelt keine Dateien: {import_dir}")
        return 2

    results: list[tuple[str, str]] = []
    for path in files:
        ext = path.suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            print(f"Ingest Video: {path.name}...")
            obj = ingest_video(str(path))
            results.append((path.name, "OK" if obj else "FAILED"))
        elif ext in AUDIO_EXTENSIONS:
            print(f"Ingest Audio: {path.name}...")
            obj = ingest_audio(str(path))
            results.append((path.name, "OK" if obj else "FAILED"))

    print("\nImport-Ergebnisse:")
    for name, status in results:
        print(f"  {name}: {status}")
    return 0 if all(status == "OK" for _, status in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        default="test_projects/Phase1_Live_Smoke_2",
        help="Projektordner relativ zum Repo-Root oder absolut.",
    )
    parser.add_argument(
        "--import-dir",
        default="test_import_phase1",
        help="Importordner relativ zum Repo-Root oder absolut.",
    )
    args = parser.parse_args()
    return run_import(_resolve_dir(args.project_dir), _resolve_dir(args.import_dir))


if __name__ == "__main__":
    raise SystemExit(main())
