import os
import sys
from pathlib import Path
PROJECT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

from sqlalchemy.orm import Session
from database import engine, VideoClip, AudioTrack

def cleanup_missing_files():
    print("Starte radikale Datenbank-Bereinigung...")
    count = 0
    with Session(engine) as session:
        # 1. Videos prüfen
        videos = session.query(VideoClip).all()
        for v in videos:
            if not v.file_path or not Path(v.file_path).exists():
                print(f"  Entferne VideoClip id={v.id}: Original fehlt -> {v.file_path}")
                session.delete(v)
                count += 1
            elif v.proxy_path and not Path(v.proxy_path).exists():
                print(f"  Leere Proxy id={v.id}: Proxy fehlt -> {v.proxy_path}")
                v.proxy_path = None
                count += 1
        
        # 2. Audio prüfen
        audios = session.query(AudioTrack).all()
        for a in audios:
            if not a.file_path or not Path(a.file_path).exists():
                print(f"  Entferne AudioTrack id={a.id}: Datei fehlt -> {a.file_path}")
                session.delete(a)
                count += 1
        
        session.commit()
    print(f"Bereinigung abgeschlossen: {count} Einträge entfernt.")

if __name__ == "__main__":
    cleanup_missing_files()
