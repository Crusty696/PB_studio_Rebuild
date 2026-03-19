import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Projektroot zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Erstellt eine temporäre In-Memory-DB für jeden Test."""
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    database.Base.metadata.create_all(test_engine)

    # Default-Projekt anlegen
    with Session(test_engine) as session:
        session.add(database.Project(name="Test", path=".", resolution="1920x1080", fps=30.0))
        session.commit()

    # Engine in allen Modulen ersetzen
    monkeypatch.setattr(database, "engine", test_engine)

    # Auch in den Service-Modulen patchen
    from services import ingest_service, audio_service
    monkeypatch.setattr(ingest_service, "engine", test_engine)
    monkeypatch.setattr(audio_service, "engine", test_engine)

    try:
        from services import video_service
        monkeypatch.setattr(video_service, "engine", test_engine)
    except ImportError:
        pass

    return test_engine
