"""Phase 1 live-smoke re-import/cache helper.

Usage:
    python scripts/phase1_cache_test.py --project-dir test_projects/Phase1_Live_Smoke_2 --import-dir test_import_phase1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from database import AudioTrack, VideoClip, engine  # noqa: E402
from services.ingest_service import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, ingest_audio, ingest_video  # noqa: E402


def _resolve_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def verify_caching(project_dir: Path, import_dir: Path) -> int:
    if not import_dir.is_dir():
        print(f"FEHLER: Import-Ordner nicht gefunden: {import_dir}")
        return 2

    project_dir.mkdir(parents=True, exist_ok=True)
    database.set_project(project_dir)

    with Session(engine) as session:
        a_count_initial = session.query(AudioTrack).count()
        v_count_initial = session.query(VideoClip).count()
        print(f"Initial: {a_count_initial} Audio, {v_count_initial} Video")

    print("\nFuehre Re-Import aus (erwarte Cache-Hits)...")
    files = sorted(import_dir.glob("*.*"))
    if not files:
        print(f"FEHLER: Import-Ordner enthaelt keine Dateien: {import_dir}")
        return 2

    for path in files:
        ext = path.suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            ingest_video(str(path))
        elif ext in AUDIO_EXTENSIONS:
            ingest_audio(str(path))

    with Session(engine) as session:
        a_count_final = session.query(AudioTrack).count()
        v_count_final = session.query(VideoClip).count()
        print(f"Final: {a_count_final} Audio, {v_count_final} Video")

    if a_count_initial == a_count_final and v_count_initial == v_count_final:
        print("\nVERIFIZIERT: Hash-Caching funktioniert. Keine Duplikate erstellt.")
        return 0

    print(
        "\nFEHLER: Duplikate gefunden! "
        f"Delta: Audio={a_count_final - a_count_initial}, "
        f"Video={v_count_final - v_count_initial}"
    )
    return 1


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
    return verify_caching(_resolve_dir(args.project_dir), _resolve_dir(args.import_dir))


if __name__ == "__main__":
    raise SystemExit(main())
