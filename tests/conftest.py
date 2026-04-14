"""
Gemeinsame Test-Fixtures fuer die PB Studio Test-Suite.

Alle Tests nutzen eine In-Memory SQLite DB – kein Datenverlust, kein
Zugriff auf die echte pb_studio.db.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Projektroot zum Suchpfad hinzufuegen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database


# ---------------------------------------------------------------------------
# Haupt-Fixture: Jeder Test bekommt seine eigene leere In-Memory-DB
# ---------------------------------------------------------------------------

@pytest.fixture
def test_engine(monkeypatch):
    """Erstellt eine isolierte In-Memory SQLite Engine pro Test.

    check_same_thread=False ist noetig weil pytest je nach Konfiguration
    Sessions in verschiedenen Threads oeffnen kann.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # FK-Enforcement in SQLite aktivieren
    from sqlalchemy import event, text

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    database.Base.metadata.create_all(engine)

    # Engine in allen relevanten Modulen ersetzen
    monkeypatch.setattr(database, "engine", engine)

    # nullpool_session() hardcodes pb_studio.db — patch it to use the test engine
    # so that worker writes go to the in-memory DB, not the production file.
    from contextlib import contextmanager as _cm

    @_cm
    def _test_nullpool():
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(database, "nullpool_session", _test_nullpool)

    # Service-Module patchen (nur wenn bereits importiert)
    for mod_name in [
        "services.ingest_service",
        "services.video_service",
        "services.ai_audio_service",
        "services.pacing_service",
        "services.audio_service",
        "services.beat_analysis_service",
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "engine"):
                monkeypatch.setattr(mod, "engine", engine)
            if hasattr(mod, "nullpool_session"):
                monkeypatch.setattr(mod, "nullpool_session", _test_nullpool)
        except ImportError:
            pass

    return engine


@pytest.fixture
def db_session(test_engine):
    """Liefert eine offene SQLAlchemy Session auf der Test-DB."""
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def project(db_session):
    """Legt ein Default-Projekt an und gibt es zurueck."""
    proj = database.Project(
        name="TestProjekt",
        path="/tmp/test",
        resolution="1920x1080",
        fps=30.0,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)
    return proj


@pytest.fixture
def audio_track(db_session, project):
    """Legt einen AudioTrack fuer Tests an."""
    track = database.AudioTrack(
        project_id=project.id,
        file_path="/tmp/test_audio.mp3",
        title="Test Audio",
        duration=180.0,
        bpm=128.0,
    )
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)
    return track


@pytest.fixture
def video_clip(db_session, project):
    """Legt einen VideoClip fuer Tests an."""
    clip = database.VideoClip(
        project_id=project.id,
        file_path="/tmp/test_video.mp4",
        duration=10.0,
        width=1920,
        height=1080,
        fps=30.0,
        codec="h264",
    )
    db_session.add(clip)
    db_session.commit()
    db_session.refresh(clip)
    return clip
