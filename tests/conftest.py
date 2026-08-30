"""
Gemeinsame Test-Fixtures fuer die PB Studio Test-Suite.

Alle Tests nutzen eine In-Memory SQLite DB – kein Datenverlust, kein
Zugriff auf die echte pb_studio.db.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Projektroot zum Suchpfad hinzufuegen
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# B-727: Guard VOR Produktimport installieren. Kindprozesse laden denselben
# Guard ueber tests/support/sitecustomize.py aus dem geerbten PYTHONPATH.
from tools.stability_manifest import discover_protected_databases
from tests.support.pb_real_db_guard import (
    configure_child_environment,
    install_guard,
)

_TEST_SUPPORT_ROOT = _REPO_ROOT / "tests" / "support"
_PROTECTED_REAL_DATABASES = discover_protected_databases(
    repo_root=_REPO_ROOT,
    appdata=Path(os.environ["APPDATA"]),
    include_missing=True,
)
configure_child_environment(
    _PROTECTED_REAL_DATABASES,
    support_root=_TEST_SUPPORT_ROOT,
)
install_guard(_PROTECTED_REAL_DATABASES)

import database


# C1 (2026-06-25): standalone diagnostic scripts, NOT pytest unit tests. They use
# a custom record()/run harness, need real GPU/video/audio data, and report failures
# via return-value/print instead of assert -> pytest counted them as always-green.
# Collecting them is misleading; run manually instead, e.g.
#   python tests/test_video_analysis_real.py
collect_ignore = [
    "test_video_analysis_real.py",
    "test_export_convert_real.py",
    "test_audio_analysis_real.py",
    "test_performance_profiling.py",
    # 2026-07-27: dieselbe Kategorie, jetzt nachgezogen. Das Modul fuehrt
    # seinen Harness beim IMPORT aus (test_core_services_deep.py:576, :871)
    # — also in der Collection, vor jeder Fixture. Dabei ruft es
    # `set_project(PROJECT_ROOT)` (:568) und schwenkt die globale Engine
    # zurueck auf die REALE pb_studio.db; anschliessend legt
    # `t_ingest_audio_real` (:844) ueber eine NamedTemporaryFile einen
    # AudioTrack an. Das war die eine Zeile, die jeder Vollauf in den
    # echten Projektdaten hinterliess.
    "test_core_services_deep.py",
    "qa_artifacts",
]


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
# B-924 — QSettings der Testsession vom echten Nutzerprofil trennen
# ---------------------------------------------------------------------------
# Qt legt QSettings unter Windows in der Registry ab. Mehrere Tests bauen
# QSettings direkt mit den Produktivnamen ("PBStudio"/"PBStudio" bzw.
# "PB Studio"/"Rebuild") und schrieben damit in HKCU\Software\PBStudio — also
# in die echte Konfiguration des Nutzers.
#
# Gefunden am 2026-08-31 im Erstlauf-Test: Nach dem vollstaendigen Loeschen
# aller App-Daten stand dort weiterhin setup_complete=true (der SetupWizard
# blieb deshalb aus), ein Onboarding-Marker sowie ein Ollama-Backend
# "http://legacy:8080" mit Modell "legacy-model" — beides woertlich aus
# tests/test_settings_migration.py. Das hatte reale Wirkung: der Testlauf
# protokollierte 122 Meldungen "B-770: gewaehltes Modell legacy-model nicht
# verfuegbar, nutze gemma3:4b".
#
# Eine Umlenkung per ``QSettings.setDefaultFormat(IniFormat)`` reicht hier
# NICHT: Der Migrationscode in ``services/settings_store.py`` liest die
# Altwerte bewusst ueber ``QSettings(org, app)`` im NativeFormat, und PySide6
# baut solche Instanzen weiterhin nativ (nachgemessen: ``qs.format()`` bleibt
# ``NativeFormat``, ``fileName()`` zeigt auf den Registry-Pfad). Die Tests
# muessen also dorthin schreiben, wo der Produktcode liest.
#
# Deshalb wird hier nicht umgelenkt, sondern zurueckgesetzt: Der Zustand der
# produktiven Zweige wird vor der Session gesichert und danach exakt
# wiederhergestellt. Was ein Test schreibt, ueberlebt die Session nicht.
#
# Ein echter Fix der Ursache braeuchte eine Produktcode-Aenderung (Format und
# Organisation im Migrationspfad injizierbar machen) — das ist eine
# Userentscheidung und hier bewusst nicht vorweggenommen.

_QSETTINGS_USER_HIVES = (
    r"HKCU\Software\PBStudio",
    r"HKCU\Software\PB Studio",
)


@pytest.fixture(scope="session", autouse=True)
def _restore_user_qsettings_after_session():
    """Stellt die QSettings-Zweige des Nutzers nach der Testsession wieder her."""
    if sys.platform != "win32":
        yield
        return

    import subprocess

    backup_dir = Path(tempfile.mkdtemp(prefix="pb_qsettings_backup_"))
    saved: dict[str, Path | None] = {}
    for hive in _QSETTINGS_USER_HIVES:
        target = backup_dir / (hive.replace("\\", "_").replace(" ", "_") + ".reg")
        result = subprocess.run(
            ["reg", "export", hive, str(target), "/y"],
            capture_output=True, check=False,
        )
        saved[hive] = target if result.returncode == 0 and target.exists() else None

    try:
        yield
    finally:
        for hive, backup in saved.items():
            subprocess.run(["reg", "delete", hive, "/f"],
                           capture_output=True, check=False)
            if backup is not None:
                subprocess.run(["reg", "import", str(backup)],
                               capture_output=True, check=False)
        shutil.rmtree(backup_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# B-727 — Schutz der realen Projekt-Datenbank (autouse, session-scoped)
# ---------------------------------------------------------------------------
# Die Default-Suite hat am 2026-07-26 nachweislich in die reale
# ``pb_studio.db`` im Repo-Root geschrieben: der ``AudioPipelineV2Worker``
# legt ueber den AnalysisStatusService Statuszeilen an (dort landeten
# audio_track_id 99 und 5 samt Fehlertext "demucs kaputt"). Der zugehoerige
# Test patchte zwar Storage- und Checkpoint-Pfade, aber nicht die globale
# DB-Engine. Die ``test_engine``-Fixture unten schuetzt nur Tests, die sie
# explizit anfordern — sie ist kein autouse und war damit kein Schutz.
#
# Dieser Guard schwenkt die globale Engine EINMAL pro Testsession auf eine
# temporaere Datei-DB um. ``database.session._get_cached_nullpool_engine()``
# leitet seine URL aus ``engine.url`` ab und folgt dem Swap automatisch —
# damit landen auch Worker-Writes ueber ``nullpool_session()`` in der Temp-DB
# statt in der Datei im Repo-Root.
#
# ``APP_ROOT`` bleibt bewusst unveraendert: Tests, die Repo-Dateien
# (config/, resources/, docs/) darueber aufloesen, sollen weiter
# funktionieren. Geschuetzt wird gezielt der DB-Schreibpfad.
#
# Tests, die selbst ``set_project()`` oder ``test_engine`` nutzen, swappen
# danach auf ihre eigene DB — das bleibt unveraendert gueltig.

@pytest.fixture(autouse=True)
def _detect_real_db_writes(request):
    """Diagnose-Netz: meldet JEDEN Test, der die reale Projekt-DB anfasst.

    Der session-scoped Guard unten leitet die globale Engine um. Er deckt
    aber nur Pfade ab, die ueber ``database.engine`` /
    ``nullpool_session()`` laufen. Tests, die sich ihre eigene Engine auf
    ``APP_ROOT/pb_studio.db`` bauen oder ``set_project()`` auf den Repo-Root
    richten, kommen weiterhin durch — genau das ist am 2026-07-27 passiert
    (analysis_status +10, audio_tracks +13, mem_pacing_run +12,
    timeline_snapshots +1 trotz aktivem Guard).

    Diese Fixture macht solche Zugriffe sofort sichtbar, statt sie erst beim
    naechsten Hash-Vergleich auffallen zu lassen.
    """
    # WICHTIG: fest verdrahteter Repo-Pfad, NICHT database.session.APP_ROOT.
    # APP_ROOT ist eine globale Variable, die set_project() umbiegt — wer sie
    # hier liest, vergleicht vor/nach dem Test womoeglich zwei verschiedene
    # Dateien und meldet Phantom-Treffer.
    real_db = _REPO_ROOT / "pb_studio.db"
    before = _db_fingerprint(real_db)
    yield
    after = _db_fingerprint(real_db)
    if before != after:
        # Der Schreiber ist nicht zwingend DIESER Test: ein Hintergrund-Thread
        # oder Subprozess kann waehrend seiner Laufzeit schreiben und ihn
        # faelschlich anschwaerzen. Deshalb hier ein Vollbild aller lebenden
        # Threads mit Stack — daraus faellt der Verursacher namentlich.
        pytest.fail(
            f"Test '{request.node.nodeid}' hat die REALE Projekt-DB "
            f"veraendert ({real_db}).\n{_live_thread_dump()}\n"
            "Tests muessen gegen die Temp-DB aus pytest_configure oder eine "
            "eigene tmp_path-DB laufen."
        )


def _db_fingerprint(path: Path) -> str | None:
    """Inhalts-Fingerabdruck der DB — NICHT die mtime.

    Ein WAL-Checkpoint schreibt die Hauptdatei neu und aendert dabei ihre
    mtime, ohne dass sich ein einziges Byte am Inhalt aendert. Ein
    mtime-Vergleich meldet dann einen Schreibzugriff, den es nie gab, und
    laesst einen unbeteiligten Test fehlschlagen. Der Hash unterscheidet
    beides zuverlaessig.
    """
    if not path.exists():
        return None
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _live_thread_dump() -> str:
    """Alle lebenden Threads mit Stack — zur Taeterermittlung beim DB-Write."""
    import threading
    import traceback

    frames = sys._current_frames()
    lines = [f"--- lebende Threads (PID {os.getpid()}) ---"]
    for thread in threading.enumerate():
        frame = frames.get(thread.ident)
        lines.append(f"  [{thread.name}] daemon={thread.daemon} alive={thread.is_alive()}")
        if frame is None:
            continue
        # Nur Projektframes — Bibliotheks-Rauschen weglassen.
        stack = [
            f"      {f.filename}:{f.lineno} in {f.name}"
            for f in traceback.extract_stack(frame)
            if str(_REPO_ROOT) in f.filename
        ]
        lines.extend(stack[-6:])
    return "\n".join(lines)


def pytest_configure(config):
    """Globale DB-Engine auf eine Temp-DB legen — VOR der Collection.

    Der Zeitpunkt ist entscheidend: pytest importiert erst alle Testmodule
    und fuehrt danach Fixtures aus. Ein session-scoped autouse-Fixture
    greift also zu SPAET — jeder Modul-Level-DB-Zugriff beim Import haette
    die reale Datei schon getroffen. Genau daran lag es, dass nach dem
    ersten Guard weiterhin Zeilen in der echten pb_studio.db landeten
    (analysis_status, audio_tracks, mem_pacing_run, timeline_snapshots).

    ``pytest_configure`` laeuft vor der Collection und schliesst die Luecke.
    """
    global _TEST_DB_ROOT, _SESSION_ENGINE

    import database.session as _session_mod
    from database.session import _make_engine

    tmp_dir = tempfile.mkdtemp(prefix="pb_studio_testdb_")
    tmp_db = Path(tmp_dir) / "pb_studio.db"

    session_engine = _make_engine(tmp_db)
    database.Base.metadata.create_all(session_engine)

    # EngineProxy.swap() disposed die alte (reale) Engine. Ab hier hat kein
    # Test mehr eine Verbindung zur Datei im Repo-Root.
    database.engine.swap(session_engine)

    # create_all deckt nur ORM-Tabellen ab. Die mem_*- und struct_*-Tabellen
    # (mem_pacing_run, mem_decision, struct_clip_tags, struct_compat_edge …)
    # existieren ausschliesslich als Alembic-Revisionen — ohne sie laufen
    # Pacing- und Enrichment-Tests gegen "no such table" und wichen frueher
    # auf die reale DB aus.
    try:
        from database.migrations import init_db as _init_db

        _init_db()
    except Exception as exc:  # pragma: no cover - Diagnose statt stillem Fehlschlag
        print(f"[conftest] Alembic-Migration der Test-DB fehlgeschlagen: {exc}")

    # NullPool-Cache invalidieren, damit er die neue URL zieht statt die
    # zwischengespeicherte Engine auf der realen DB weiterzureichen.
    with _session_mod._NULLPOOL_ENGINE_CACHE_LOCK:
        _session_mod._nullpool_engine_cache = None

    _TEST_DB_ROOT = Path(tmp_dir)
    _SESSION_ENGINE = session_engine

    # Kindprozesse (main.py mit PB_CLUSTER_FIT / PB_WAVEFORM_PARSE) erben die
    # Umgebung, aber keinen Monkeypatch. Ohne diesen Override oeffnen sie die
    # echte Projekt-DB — genau darueber liefen trotz Guard noch Schreibzugriffe.
    os.environ["PB_STUDIO_DB_PATH"] = str(tmp_db)

    _install_real_db_connect_guard()


def _install_real_db_connect_guard():
    """Jede sqlite3-Verbindung zur REALEN Projekt-DB hart unterbinden.

    Der mtime-Vergleich pro Test sagt nur DASS geschrieben wurde, nicht von
    WEM — bei Hintergrund-Threads schwaerzt er sogar den falschen Test an.
    Dieser Guard setzt an der einzigen Stelle an, die alle Wege teilen:
    ``sqlite3.connect``. Wer die Datei im Repo-Root oeffnen will, bekommt
    einen Fehler MIT Stacktrace statt still zu schreiben.

    Auch lesende URI-Verbindungen (``mode=ro``) werden blockiert: Diagnose-
    Skripte muessen eine externe RAW-Kopie inspizieren, nie das Original.
    """
    install_guard(_PROTECTED_REAL_DATABASES)


def pytest_unconfigure(config):
    """Temp-DB nach dem Lauf aufraeumen."""
    global _SESSION_ENGINE
    if _SESSION_ENGINE is not None:
        try:
            _SESSION_ENGINE.dispose()
        except Exception:  # pragma: no cover
            pass
        _SESSION_ENGINE = None
    if _TEST_DB_ROOT is not None:
        shutil.rmtree(_TEST_DB_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def _protect_real_database():
    """Pfad der Session-Temp-DB (der Swap selbst passiert in pytest_configure)."""
    assert _TEST_DB_ROOT is not None, "pytest_configure hat die Temp-DB nicht gesetzt"
    return _TEST_DB_ROOT / "pb_studio.db"


# Projektwurzel der Session-Temp-DB. Tests, die ``set_project()`` aufrufen,
# muessen HIERHIN zuruecksetzen — nicht auf das Repo-Root und nicht auf
# ``Path.cwd()``, sonst zeigt die globale Engine wieder auf die reale
# ``pb_studio.db`` und alle nachfolgenden Tests schreiben dorthin.
_TEST_DB_ROOT: Path | None = None
_SESSION_ENGINE = None


@pytest.fixture
def test_db_root(_protect_real_database) -> Path:
    """Wurzelverzeichnis der Session-Temp-DB (fuer ``set_project``-Rueckkehr)."""
    return _protect_real_database.parent


@pytest.fixture(autouse=True)
def _restore_engine_after_project_switch():
    """Repariert die globale Engine, falls ein Test sie umgeschwenkt hat.

    ``set_project()`` ist ein globaler Seiteneffekt. Ein Test, der es
    aufruft und danach auf Repo-Root/``cwd`` zuruecksetzt, richtet die
    Engine auf die reale Projekt-DB — ab dann schreibt JEDER folgende Test
    dorthin, ohne selbst schuld zu sein. Genau so entstanden am 2026-07-27
    trotz aktivem Session-Guard 10 neue analysis_status-, 13 audio_tracks-,
    12 mem_pacing_run- und 1 timeline_snapshots-Zeile in der echten DB.

    Diese Fixture stellt nach jedem Test den Session-Zustand wieder her.
    """
    yield
    if _TEST_DB_ROOT is None:
        return
    import database.session as _session_mod

    expected = (_TEST_DB_ROOT / "pb_studio.db").resolve()
    try:
        current = Path(str(database.engine.url).replace("sqlite:///", "")).resolve()
    except Exception:  # pragma: no cover - defekte Engine nicht verschlimmern
        return
    if current == expected:
        return

    from database.session import _make_engine

    repaired = _make_engine(expected)
    database.Base.metadata.create_all(repaired)
    database.engine.swap(repaired)
    with _session_mod._NULLPOOL_ENGINE_CACHE_LOCK:
        _session_mod._nullpool_engine_cache = None
    # APP_ROOT auf den ORIGINALWERT zuruecksetzen, nicht auf den Temp-Pfad:
    # der Session-Guard laesst APP_ROOT bewusst unangetastet, damit Tests
    # weiter Repo-Dateien (config/, resources/) darueber aufloesen koennen.
    # Ihn hier auf die Temp-DB zu biegen waere ein neuer globaler
    # Seiteneffekt fuer alle Folgetests.
    _session_mod.APP_ROOT = _REPO_ROOT


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
        "services.analysis_status_service",
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
