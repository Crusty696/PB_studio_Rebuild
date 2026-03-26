"""
Bereinigt pb_studio.db von Test-Datensaetzen.

Loescht alle Eintraege, deren Pfade '/tmp/' oder 'pytest' enthalten –
also Daten, die von E2E-Tests oder pytest-Laeufen hinterlassen wurden.

Aufruf:
    python tests/db_cleanup.py
"""
import sys
from pathlib import Path

# Projektroot in Suchpfad
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database
from database import init_db
from sqlalchemy.orm import Session

TEST_PATTERNS = ("/tmp/", "pytest", "pb_e2e_")


def _is_test_path(path: str | None) -> bool:
    if not path:
        return False
    return any(p in path for p in TEST_PATTERNS)


def cleanup():
    init_db()
    removed = 0

    with Session(database.engine) as session:
        # AudioTracks mit Test-Pfaden entfernen (cascade loescht beatgrids, waveforms)
        tracks = session.query(database.AudioTrack).all()
        for t in tracks:
            if _is_test_path(t.file_path):
                print(f"  Entferne AudioTrack id={t.id}: {t.file_path}")
                session.delete(t)
                removed += 1

        # VideoClips mit Test-Pfaden entfernen (cascade loescht scenes)
        clips = session.query(database.VideoClip).all()
        for c in clips:
            if _is_test_path(c.file_path):
                print(f"  Entferne VideoClip id={c.id}: {c.file_path}")
                session.delete(c)
                removed += 1

        session.commit()

    print(f"\nBereinigung abgeschlossen: {removed} Testdatensatz/saetze entfernt.")


if __name__ == "__main__":
    cleanup()
