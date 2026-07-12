import logging
import sys
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from services.timeout_constants import (
    DB_BUSY_TIMEOUT_ANALYSIS_MS,
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
                # B-192: session.close() in try-catch wrappen — sonst kann
                # ein Close-Error im Cleanup-Pfad die Original-Exception
                # ueberschreiben (Python __exit__-Semantik: ein selbst-
                # geworfener Exit-Error verschluckt das exc_val des
                # ``with``-Blocks).
                try:
                    self._session.close()
                except Exception as close_err:  # broad catch intentional — close() can fail on broken connection
                    logger.warning("session.close() fehlgeschlagen: %s", close_err)
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


# FREEZE-Fix 2026-07-10: get_active_project_id wird aus UI-Klick-Pfaden
# (Workspace-Wechsel, Gates) aufgerufen. Als DB-Query blockierte sie bei
# busy DB (Hintergrund-Writer + busy_timeout) den Main-Thread sekundenlang
# (freeze_stacks-Watchdog: 9 Dumps auf dieser Zeile). Pro Projekt-DB gibt es
# genau ein aktives Projekt; die ID aendert sich nur mit der Engine
# (set_project-Swap) oder wenn das Projekt-Row erst noch entsteht. Der Cache
# ist an die Identitaet der ECHTEN Engine gebunden — jeder Engine-Wechsel
# (set_project, Test-Patch) macht ihn automatisch ungueltig, ohne dass eine
# Stelle explizit invalidieren muss. None wird bewusst NICHT gecacht
# (Default-Projekt kann kurz nach Boot entstehen). Kein Soft-Delete-Pfad
# setzt Project.deleted_at (repo-weit verifiziert 2026-07-10).
_active_project_id_cache: tuple[int, int] | None = None  # (id(engine), project_id)


def _invalidate_active_project_id_cache() -> None:
    global _active_project_id_cache
    _active_project_id_cache = None


def get_active_project_id() -> int | None:
    """Gibt die ID des aktiven Projekts zurueck (erstes in der DB, oder None).

    H9-FIX: Kein Fallback auf ID=1 mehr — das konnte auf ein nicht-existentes
    Projekt verweisen. Caller muessen mit None umgehen koennen.
    """
    global _active_project_id_cache
    try:
        eng_key = id(object.__getattribute__(engine, '_engine'))
    except AttributeError:
        eng_key = id(engine)
    if _active_project_id_cache is not None and _active_project_id_cache[0] == eng_key:
        return _active_project_id_cache[1]
    try:
        from database.models import Project
        with Session(engine) as s:
            proj = s.query(Project).filter(Project.deleted_at.is_(None)).first()
            if proj is not None:
                _active_project_id_cache = (eng_key, proj.id)
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

    # H-6: Alte VectorDB-Instanz sauber schliessen (expliziter
    # WAL-Checkpoint) BEVOR der Singleton-Reset sie verwaist — sonst
    # bleiben embeddings.db-wal/-shm Sidecars des alten Projekts zurueck.
    _vdb_mod = sys.modules.get("services.vector_db_service")
    if _vdb_mod is not None:
        _old_vdb = getattr(_vdb_mod, "_instance", None)
        if _old_vdb is not None:
            try:
                _old_vdb.close()
            except Exception as exc:  # Project-Switch darf hieran nicht scheitern
                logger.warning(
                    "VectorDB close() vor Singleton-Reset fehlgeschlagen: %s", exc
                )

    patches = {
        "services.vector_db_service": {
            "_instance": None,  # F-030: Singleton reset on project switch
        },
    }
    for mod_name, attrs in patches.items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            for attr, value in attrs.items():
                setattr(mod, attr, value)
                logger.debug("Patched %s.%s -> %s", mod_name, attr, value)


def _running_tasks_block_reason(exclude_task_id: str | None = None) -> str | None:
    """B-490 Followup (CRF-005): laufende TaskManager-Tasks ermitteln.

    Returns:
        Beschreibung der laufenden Tasks (fuer die Fehlermeldung) oder
        ``None`` wenn keine laufen bzw. der TaskManager nicht verfuegbar
        ist (Headless-Skripte/Tests ohne QApplication — dort existieren
        keine Hintergrund-Tasks).

    Lazy import vermeidet den Import-Zyklus database -> services
    (gleiches Pattern wie ``ProjectManager._has_running_tasks``).
    """
    try:
        from services.task_manager import GlobalTaskManager
        tm = GlobalTaskManager.instance()
        running = [
            t for t in tm.get_all_tasks()
            if getattr(t, "status", None) == "running"
            and (exclude_task_id is None
                 or getattr(t, "task_id", None) != exclude_task_id)
        ]
    except (ImportError, AttributeError, RuntimeError):
        # Kein QApplication / TaskManager nicht initialisiert -> keine Tasks.
        return None
    if not running:
        return None
    names = ", ".join(str(getattr(t, "name", "?")) for t in running[:5])
    return f"{len(running)} laufende(r) Task(s): {names}"


def set_project(
    project_path: Path,
    *,
    exclude_task_id: str | None = None,
    force: bool = False,
):
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

    B-490 Followup (CRF-005): Wenn der GlobalTaskManager laufende Tasks
    meldet, wird der Engine-Swap mit ``RuntimeError`` ABGELEHNT statt nur
    zu warnen (vorher M-42: Log-Warnung). Ein Swap mid-run liess Worker
    still in die falsche Projekt-DB schreiben bzw. FK-crashen.

    Args:
        exclude_task_id: Eigene Task-ID des Aufrufers — ein Worker, der den
            Projektwechsel selbst ausfuehrt (ProjectManager.open_project im
            OpenWorker, B-047), zaehlt nicht als blockierender Task.
        force: Nur fuer interne Recovery-Pfade (B-051-Rollback nach
            init_db-Fehler) — Swap trotz laufender Tasks, mit Warn-Log.

    Raises:
        RuntimeError: wenn laufende Tasks existieren und ``force`` False ist.
    """
    global APP_ROOT
    project_path = Path(project_path)
    db_file = project_path / "pb_studio.db"

    # B-490 Followup (CRF-005): harte Sperre statt M-42-Log-Warnung.
    block_reason = _running_tasks_block_reason(exclude_task_id=exclude_task_id)
    if block_reason is not None:
        if force:
            logger.warning(
                "set_project(force=True) trotz laufender Tasks (%s) — "
                "Recovery-Pfad, Caller uebernimmt Verantwortung.", block_reason,
            )
        else:
            raise RuntimeError(
                "Projektwechsel erst nach Abschluss/Abbruch laufender Tasks "
                f"moeglich — {block_reason}"
            )

    # FIX H-7: Create engine inside lock to prevent race window
    with _APP_ROOT_LOCK:
        new_engine = _make_engine(db_file)

        # B-135 Fix: Tabellen BEVOR dem swap erstellen, sodass kein
        # Caller jemals eine Engine ohne Tabellen sieht. Vorher
        # passierte init_db() als separater Call NACH set_project —
        # Race-Window in dem ein Auto-Refresh-Reader auf eine leere
        # DB stoßen konnte ("no such table").
        try:
            from database.models import Base
            Base.metadata.create_all(new_engine)
        except Exception as create_err:
            logger.warning(
                "set_project: create_all auf neuer Engine fehlgeschlagen "
                "(Caller muss init_db() ggf. selbst erneut versuchen): %s",
                create_err,
            )

        engine.swap(new_engine)
        APP_ROOT = project_path
        # FREEZE-Fix 2026-07-10: Projekt-ID-Cache gehoert zur alten Engine.
        _invalidate_active_project_id_cache()
        _patch_service_paths(project_path)

        # B-133 + B-134: alter dead-code Block entfernt — engine._proxied
        # existierte nie (EngineProxy nutzt _engine), und der
        # time.sleep(0.1) war ein Race-Hack der den Lock 100 ms hielt.
        # EngineProxy.swap() macht bereits den disposal — keine zweite
        # Phase noetig.

    logger.info("Projekt gewechselt: %s", project_path)
