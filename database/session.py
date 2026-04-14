import logging
import sys
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from services.timeout_constants import (
    DB_BUSY_TIMEOUT_ANALYSIS_MS,
    DB_BUSY_TIMEOUT_MS,
    DB_POOL_TIMEOUT_SEC,
    DB_SQLITE_CONNECT_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

# Zentraler Projektpfad — alle Services importieren APP_ROOT statt relative Pfade zu nutzen
# F-019: .resolve() stellt sicher dass der Pfad immer absolut ist (unabhaengig von CWD)
APP_ROOT = Path(__file__).resolve().parent.parent

# P0-FIX: Threading lock for APP_ROOT mutation to prevent race conditions
_APP_ROOT_LOCK = threading.Lock()


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

    M6-FIX: RLock schuetzt swap() und alle Zugriffe, damit andere Threads
    waehrend eines swap() nicht die alte (disposed) Engine erwischen.
    """

    def __init__(self, real_engine):
        object.__setattr__(self, '_engine', real_engine)
        object.__setattr__(self, '_lock', threading.RLock())

    def __getattr__(self, name):
        with object.__getattribute__(self, '_lock'):
            return getattr(object.__getattribute__(self, '_engine'), name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the real engine."""
        with object.__getattribute__(self, '_lock'):
            setattr(object.__getattribute__(self, '_engine'), name, value)

    def swap(self, new_engine):
        """Atomically replace the wrapped engine; dispose the old one."""
        with object.__getattribute__(self, '_lock'):
            old = object.__getattribute__(self, '_engine')
            object.__setattr__(self, '_engine', new_engine)
        # dispose() ausserhalb des Locks — kann langsam sein und braucht keinen Lock
        try:
            old.dispose()
        except Exception as e:  # broad catch intentional — dispose() can raise various engine errors
            logger.warning("EngineProxy.swap() — old.dispose() fehlgeschlagen: %s", e)

    # Explicit delegates needed for SQLAlchemy internals that bypass __getattr__:
    def connect(self, *a, **kw):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').connect(*a, **kw)

    def begin(self, *a, **kw):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').begin(*a, **kw)

    def dispose(self, *a, **kw):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').dispose(*a, **kw)

    @property
    def dialect(self):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').dialect

    @property
    def url(self):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').url

    @property
    def pool(self):
        with object.__getattribute__(self, '_lock'):
            return object.__getattribute__(self, '_engine').pool


def _make_engine(db_path: Path):
    """Create a configured SQLAlchemy engine with FK/WAL/sync pragmas.

    The pragma setup is done via an event listener attached to each new
    engine instance (not a global decorator).

    P3-FIX: SQLite Transaction Isolation: SQLite in WAL mode uses SERIALIZABLE
    by default, which is appropriate for this application. READ COMMITTED is
    not fully supported in SQLite and SERIALIZABLE is the recommended mode
    for WAL (Write-Ahead Logging) to ensure data consistency.
    """
    eng = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": DB_SQLITE_CONNECT_TIMEOUT_SEC},
        # Pool fuer schnelle Reads. Worker nutzen nullpool_session() fuer Writes.
        # pool_size=10 idle Connections, max_overflow=30 Burst-Kapazitaet
        # (P7-FIX): vorher 5+15=20, das reicht nicht bei 3+ parallelen Workern
        # (StemSeparator, AutoEdit mit 101 Clips, Export, Main-Thread UI-Reads,
        # periodischer "Medien-DB laden"-Task). Gemessener Peak-Bedarf: ~12-20.
        # Neuer Headroom 40 liefert Puffer, ohne SQLite zu ueberfordern.
        pool_size=10,
        max_overflow=30,
        pool_timeout=DB_POOL_TIMEOUT_SEC,
        pool_recycle=300,
    )

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # WAL-optimiert: fsync nur bei Checkpoint
        cursor.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_ANALYSIS_MS}")  # 120s warten bei locked DB (Multi-Worker + lange Analyse)
        cursor.close()

    # Pool-Diagnose: Logge Warnung wenn Pool-Overflow-Bereich erreicht wird
    _pool_max = eng.pool.size() + eng.pool._max_overflow
    @event.listens_for(eng.pool, "checkout")
    def _on_pool_checkout(dbapi_connection, connection_record, connection_proxy):
        checked_out = eng.pool.checkedout()
        if checked_out >= eng.pool.size():  # Overflow-Bereich erreicht
            logger.warning(
                "[DB-Pool] Hohe Auslastung: %d/%d Connections checked out",
                checked_out, _pool_max,
            )

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
        connect_args={"check_same_thread": False, "timeout": DB_SQLITE_CONNECT_TIMEOUT_SEC},
        poolclass=NullPool,
    )

    @_ev.listens_for(_eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        # P1-FIX: Konsistenz mit Haupt-Engine (120s für Worker-Threads mit langen Ops)
        c.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_ANALYSIS_MS}")
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    return _NullPoolSessionContext(_eng)


class _NullPoolSessionContext:
    """Context-Manager fuer NullPool-Sessions. Disposed die Engine beim Verlassen.

    M5-FIX: Auto-Commit wird uebersprungen wenn der Caller bereits explizit
    ``session.commit()`` oder ``session.rollback()`` aufgerufen hat. Dadurch
    werden doppelte Commits und Commits nach Rollback vermieden.
    """

    def __init__(self, eng):
        self._eng = eng
        self._session = None
        self._explicitly_committed = False
        self._explicitly_rolled_back = False

    def __enter__(self):
        self._session = _TrackedSession(self._eng, self)
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._session is not None:
                if exc_type is not None:
                    # Exception im with-Block: Rollback
                    if not self._explicitly_rolled_back:
                        try:
                            self._session.rollback()
                        except Exception as rb_err:  # broad catch intentional — rollback itself can fail on closed connection
                            logger.warning("session.rollback() fehlgeschlagen: %s", rb_err)
                elif not self._explicitly_committed and not self._explicitly_rolled_back:
                    # M5-FIX: Auto-commit NUR wenn weder commit() noch rollback()
                    # explizit aufgerufen wurden
                    try:
                        self._session.commit()
                    except Exception as commit_err:  # broad catch intentional — commit can fail on DB constraints
                        logger.warning("session.commit() fehlgeschlagen: %s", commit_err)
                        try:
                            self._session.rollback()
                        except Exception as rb_err:  # rollback after failed commit
                            logger.warning("session.rollback() nach fehlgeschlagenem commit: %s", rb_err)
                        raise  # Re-raise commit error so caller knows operation failed
                self._session.close()
        finally:
            # B-008 Fix: dispose() Fehler abfangen statt still zu schlucken
            try:
                self._eng.dispose()
            except Exception as dispose_err:  # broad catch intentional — dispose() can raise various engine errors
                logger.warning("engine.dispose() fehlgeschlagen: %s", dispose_err)
        return False


class _TrackedSession(Session):
    """M5-FIX: Session-Subklasse die commit/rollback Aufrufe tracked."""

    def __init__(self, eng, ctx: _NullPoolSessionContext):
        super().__init__(eng)
        self._ctx = ctx

    def commit(self):
        self._ctx._explicitly_committed = True
        return super().commit()

    def rollback(self):
        self._ctx._explicitly_rolled_back = True
        return super().rollback()


def get_active_project_id() -> int | None:
    """Gibt die ID des aktiven Projekts zurueck (erstes in der DB, oder None).

    H9-FIX: Kein Fallback auf ID=1 mehr — das konnte auf ein nicht-existentes
    Projekt verweisen. Caller muessen mit None umgehen koennen.
    """
    try:
        from database.models import Project
        with Session(engine) as s:
            proj = s.query(Project).filter(Project.deleted_at.is_(None)).first()
            if proj is not None:
                return proj.id
            logger.warning("get_active_project_id(): Kein aktives Projekt in der DB gefunden")
            return None
    except Exception as e:  # broad catch intentional — fallback if DB is unavailable at startup
        logger.warning("get_active_project_id() failed: %s", e)
        return None


def _patch_service_paths(project_path: Path):
    """Patch module-level path constants in service modules to point at the
    new project folder.  Uses ``sys.modules`` so already-imported modules
    get updated in-place.
    """
    # ai_audio_service, export_service, timeline_service, video_service,
    # convert_service, video_analysis_service no longer need patching
    # — they use lazy getter functions that re-read APP_ROOT at call time (BUG-002 fix)
    patches = {
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

    MEDIUM-10 AUDIT: Globale APP_ROOT Mutation via Lock.
    Alternativ waere ProjectContext DI, aber das wuerde einen
    grossen Refactor aller 30+ Service-Module erfordern.
    Aktueller Ansatz ist thread-safe via _APP_ROOT_LOCK.

    - Creates a new engine via ``_make_engine``
    - Atomically swaps it into the global ``engine`` proxy
    - Updates ``APP_ROOT``
    - Patches service module-level path constants

    Thread-safe: Uses _APP_ROOT_LOCK to prevent race conditions during project switch.
    """
    global APP_ROOT
    project_path = Path(project_path)
    db_file = project_path / "pb_studio.db"

    # FIX H-7: Create engine inside lock to prevent race window
    with _APP_ROOT_LOCK:
        new_engine = _make_engine(db_file)
        engine.swap(new_engine)
        APP_ROOT = project_path
        _patch_service_paths(project_path)

    logger.info("Projekt gewechselt: %s", project_path)
