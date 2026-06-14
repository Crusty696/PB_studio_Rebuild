"""
Gemeinsame Test-Fixtures fuer die PB Studio Test-Suite.

Alle Tests nutzen eine In-Memory SQLite DB – kein Datenverlust, kein
Zugriff auf die echte pb_studio.db.
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Projektroot zum Suchpfad hinzufuegen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database


# ---------------------------------------------------------------------------
# PySide6 auto-skip — verhindert die Cross-Venv-Verwirrung aus 2026-04-25:
# Default-`python` (3.14) hat kein PySide6, `.venv`-Python (3.10/3.11) hat es.
# Tests, die PySide6 / PySide6-abhaengige Module importieren, werden
# automatisch geskipped wenn das Modul nicht da ist — statt mit einem rohen
# CollectionError abzubrechen.
# ---------------------------------------------------------------------------
try:
    import PySide6  # noqa: F401
    _PYSIDE6_AVAILABLE = True
except ImportError:
    _PYSIDE6_AVAILABLE = False


def pytest_collection_modifyitems(config, items):
    """Auto-skip Qt-/Pacing-/Worker-Tests bei fehlendem PySide6.

    Heuristik: Test-Modul-Source enthaelt ``PySide6`` oder importiert
    Module, die PySide6 transitiv ziehen (workers, ui, services.actions).
    """
    if _PYSIDE6_AVAILABLE:
        return
    skip_marker = pytest.mark.skip(
        reason="PySide6 not installed — run via .venv python (3.10/3.11)"
    )
    qt_dependent_prefixes = ("workers.", "ui.", "services.actions.")
    for item in items:
        mod_file = getattr(item.module, "__file__", None) if hasattr(item, "module") else None
        if not mod_file:
            continue
        try:
            with open(mod_file, "r", encoding="utf-8") as f:
                src = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if "PySide6" in src or any(p in src for p in qt_dependent_prefixes):
            item.add_marker(skip_marker)


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
        poolclass=StaticPool,
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


# ---------------------------------------------------------------------------
# Compatibility aliases for real-data test scripts (test_audio_analysis_real,
# test_video_analysis_real). Those tests were originally written as standalone
# scripts with positional args; pytest discovery needs parameter-named fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(test_engine):
    """Alias for `test_engine` — some real-data tests use the shorter name."""
    return test_engine


@pytest.fixture
def project_id(project):
    """The INT id of the default project fixture."""
    return project.id


# ---------------------------------------------------------------------------
# Qt — session-scoped QApplication (T6.2)
# ---------------------------------------------------------------------------
# Bisher hatten viele Tests einen lokalen `_qapp()`-Helper. Diese Fixture
# stellt eine einzige QApplication-Instanz pro Session bereit und vermeidet
# Multiple-QApplication-Warnungen. Tests duerfen `_qapp()` weiter nutzen
# (idempotent), neue Tests sollten die `qapp`-Fixture verwenden.

@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication, offscreen.

    Bei fehlendem PySide6 wird der Test ohnehin durch
    `pytest_collection_modifyitems` geskipped.
    """
    if not _PYSIDE6_AVAILABLE:
        pytest.skip("PySide6 not installed")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication  # local import — see skip
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# SCHNITT — patched engine helper (T6.3)
# ---------------------------------------------------------------------------
# Patcht die `engine`-Referenz in allen relevanten SCHNITT-Service-Modulen
# auf die test_engine. Konsumenten muessen damit nicht mehr selbst
# `monkeypatch.setattr(...)` pro Modul aufrufen.

@pytest.fixture
def patched_schnitt_engine(test_engine, monkeypatch):
    """Patcht engine in allen SCHNITT-Service-Modulen.

    Lazy-Imports: Module die noch nicht geladen sind werden ueberspringen.
    """
    import importlib
    for mod_name in [
        "services.project_notes_service",
        "services.timeline_state",
        "services.timeline_snapshot_service",
    ]:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, "engine"):
            monkeypatch.setattr(mod, "engine", test_engine)
    yield test_engine


@pytest.fixture
def tmp_storage_root(tmp_path):
    """Synthetic Plan-C storage root with a ready `by_sha/` directory."""

    root = tmp_path / "global_storage"
    (root / "by_sha").mkdir(parents=True)
    return root


@pytest.fixture
def mock_v2_stems(tmp_path):
    """Legacy project-local V2 stem layout for storage migration tests."""

    project_root = tmp_path / "project"
    source = tmp_path / "track.wav"
    source.write_bytes(b"audio-source")
    stem_dir = project_root / "storage" / "stems" / "1"
    stem_dir.mkdir(parents=True)
    stems = {
        "vocals": stem_dir / "vocals.flac",
        "drums": stem_dir / "drums.flac",
        "bass": stem_dir / "bass.flac",
        "other": stem_dir / "other.flac",
    }
    for role, path in stems.items():
        path.write_bytes(role.encode("ascii"))
    return {
        "project_root": project_root,
        "source": source,
        "stem_dir": stem_dir,
        "stems": stems,
    }


@pytest.fixture
def directory_link_factory():
    """Create a junction/symlink with the production helper."""

    from services.storage_provenance.layout import create_directory_link

    def _create(link_path, target_dir):
        return create_directory_link(link_path, target_dir)

    return _create


@pytest.fixture
def mock_project_with_artifacts(tmp_path, tmp_storage_root):
    """Complete offline project setup with provenance DB rows and by_sha artifact."""

    from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
    from services.storage_provenance.source_identity import compute_source_sha256

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video-source")
    source_sha = compute_source_sha256(source, media_type="video", mode="strict")
    artifact = tmp_storage_root / "by_sha" / source_sha[:2] / source_sha / "video" / "proxy.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"proxy")

    project = Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0)
    session.add(project)
    session.add(
        ProjectSource(
            project_id=1,
            source_sha256=source_sha,
            current_source_path=str(source),
        )
    )
    job = AnalysisJob(
        source_sha256=source_sha,
        step_id="video.plan_a.outputs",
        step_version="1",
        params_hash="params",
        status="done",
    )
    job.artifacts.append(
        AnalysisArtifact(
            artifact_type="video",
            artifact_role="proxy",
            path="video/proxy.mp4",
            bytes=artifact.stat().st_size,
        )
    )
    session.add(job)
    session.commit()

    try:
        yield {
            "session": session,
            "storage_root": tmp_storage_root,
            "project_id": project.id,
            "source": source,
            "source_sha": source_sha,
            "artifact": artifact,
        }
    finally:
        session.close()
