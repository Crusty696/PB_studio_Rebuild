import logging
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Zentraler Projektpfad — alle Services importieren APP_ROOT statt relative Pfade zu nutzen
# F-019: .resolve() stellt sicher dass der Pfad immer absolut ist (unabhaengig von CWD)
APP_ROOT = Path(__file__).resolve().parent.parent


# ======================================================================
# EngineProxy — transparenter Wrapper um die echte SQLAlchemy Engine.
# Ermoeglicht atomaren Engine-Swap bei Projektwechsel, ohne dass
# Module die ``from database import engine`` gemacht haben neu
# importiert werden muessen.
# ======================================================================

class EngineProxy:
    """Transparent proxy that forwards all attribute access to the real engine.

    Call ``swap(new_engine)`` to atomically replace the inner engine and
    dispose the old one.  All existing references (``Session(engine)``,
    ``Base.metadata.create_all(engine)``) keep working because they go
    through this proxy.
    """

    def __init__(self, real_engine):
        object.__setattr__(self, '_engine', real_engine)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_engine'), name)

    def swap(self, new_engine):
        """Atomically replace the wrapped engine; dispose the old one."""
        old = object.__getattribute__(self, '_engine')
        object.__setattr__(self, '_engine', new_engine)
        try:
            old.dispose()
        except Exception as e:
            logger.warning("EngineProxy.swap() — old.dispose() fehlgeschlagen: %s", e)

    # Explicit delegates needed for SQLAlchemy internals that bypass __getattr__:
    def connect(self, *a, **kw):
        return object.__getattribute__(self, '_engine').connect(*a, **kw)

    def begin(self, *a, **kw):
        return object.__getattribute__(self, '_engine').begin(*a, **kw)

    def dispose(self, *a, **kw):
        return object.__getattribute__(self, '_engine').dispose(*a, **kw)

    @property
    def dialect(self):
        return object.__getattribute__(self, '_engine').dialect

    @property
    def url(self):
        return object.__getattribute__(self, '_engine').url

    @property
    def pool(self):
        return object.__getattribute__(self, '_engine').pool


def _make_engine(db_path: Path):
    """Create a configured SQLAlchemy engine with FK/WAL/sync pragmas.

    The pragma setup is done via an event listener attached to each new
    engine instance (not a global decorator).
    """
    eng = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 60},
        # Pool fuer schnelle Reads. Worker nutzen nullpool_session() fuer Writes.
        # pool_size=5 idle Connections, max_overflow=15 Burst-Kapazitaet fuer
        # Batch-Operationen (z.B. 10+ Video-Clips gleichzeitig laden).
        pool_size=5,
        max_overflow=15,
        pool_timeout=60,
        pool_recycle=300,
    )

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # WAL-optimiert: fsync nur bei Checkpoint
        cursor.execute("PRAGMA busy_timeout=120000")  # 120s warten bei locked DB (Multi-Worker + lange Analyse)
        cursor.close()

    return eng


# Datenbank-Engine: SQLite-Datei im Projektordner
# check_same_thread=False ist ZWINGEND noetig, weil QThread-Workers
# auf dieselbe Engine zugreifen (SQLite verbietet sonst Cross-Thread-Zugriff).
engine = EngineProxy(_make_engine(APP_ROOT / 'pb_studio.db'))


def get_raw_engine():
    """Return the ACTUAL SQLAlchemy engine (not the proxy).

    Needed for ``sqlalchemy.inspect()`` which requires a real engine instance.
    """
    return object.__getattribute__(engine, '_engine')


def nullpool_session():
    """Erzeugt eine SQLAlchemy Session mit NullPool-Engine (frische Connection).

    Verwendung fuer Worker-Threads die in die DB schreiben und dabei
    "database is locked" Fehler durch den Connection Pool bekommen.
    Die NullPool-Engine erstellt eine frische Connection pro Session und
    schliesst sie sofort nach dem Commit — kein Pooling, kein Lock-Halten.

    Muster (identisch mit timeline_service._do_apply_segments):
        with nullpool_session() as session:
            track = session.get(AudioTrack, track_id)
            track.bpm = 120.0
            session.commit()

    Die Engine wird automatisch disposed wenn der Context-Manager endet.
    """
    from sqlalchemy import create_engine as _ce, event as _ev
    from sqlalchemy.pool import NullPool

    _eng = _ce(
        str(engine.url),
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )

    @_ev.listens_for(_eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    return _NullPoolSessionContext(_eng)


class _NullPoolSessionContext:
    """Context-Manager fuer NullPool-Sessions. Disposed die Engine beim Verlassen."""

    def __init__(self, eng):
        self._eng = eng
        self._session = None

    def __enter__(self):
        self._session = Session(self._eng)
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._session is not None:
                self._session.close()
        finally:
            # B-008 Fix: dispose() Fehler abfangen statt still zu schlucken
            try:
                self._eng.dispose()
            except Exception as dispose_err:
                logger.warning("engine.dispose() fehlgeschlagen: %s", dispose_err)
        return False


def get_active_project_id() -> int:
    """Gibt die ID des aktiven Projekts zurueck (erstes in der DB, Default=1)."""
    try:
        from database.models import Project
        with Session(engine) as s:
            proj = s.query(Project).first()
            return proj.id if proj else 1
    except Exception:
        return 1


def _patch_service_paths(project_path: Path):
    """Patch module-level path constants in service modules to point at the
    new project folder.  Uses ``sys.modules`` so already-imported modules
    get updated in-place.
    """
    # video_service, convert_service, video_analysis_service no longer need patching
    # — they use lazy getter functions that re-read APP_ROOT at call time (BUG-002 fix)
    patches = {
        "services.ai_audio_service": {"STEMS_DIR": project_path / "storage" / "stems"},
        "services.export_service": {"EXPORT_DIR": project_path / "exports"},
        "services.vector_db_service": {
            "DB_DIR": project_path / "data" / "vector",
            "DB_FILE": project_path / "data" / "vector" / "embeddings.db",
            "_instance": None,  # F-030: Singleton reset on project switch
        },
    }
    for mod_name, attrs in patches.items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            for attr, value in attrs.items():
                setattr(mod, attr, value)
                logger.debug("Patched %s.%s -> %s", mod_name, attr, value)


def set_project(project_path: Path):
    """Switch the active project to *project_path*.

    - Creates a new engine via ``_make_engine``
    - Atomically swaps it into the global ``engine`` proxy
    - Updates ``APP_ROOT``
    - Patches service module-level path constants
    """
    global APP_ROOT
    project_path = Path(project_path)
    db_file = project_path / "pb_studio.db"

    new_engine = _make_engine(db_file)
    engine.swap(new_engine)
    APP_ROOT = project_path
    _patch_service_paths(project_path)
    logger.info("Projekt gewechselt: %s", project_path)
