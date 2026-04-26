"""PB Studio — Project Manager (Create / Open / Save-As).

Handles project lifecycle: creating new projects, opening existing ones,
and saving the current project to a new location. Each project is a folder
containing a pb_studio.db plus storage sub-directories.
"""

import logging
import shutil
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class ProjectManager(QObject):
    """Manages project lifecycle (create / open / save-as).

    Emits ``project_changed(path)`` after every successful switch so the UI
    can refresh tables, timeline, window title, etc.
    """

    # Use ``object`` instead of ``Path`` for Signal compatibility across threads.
    project_changed = Signal(object)

    # Sub-directories every project folder must contain.
    _SUBDIRS = [
        "storage/proxies",
        "storage/keyframes",
        "storage/stems",
        "exports",
        "data/vector",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_dirs(project_path: Path):
        """Create the standard sub-directory tree inside *project_path*."""
        for sub in ProjectManager._SUBDIRS:
            (project_path / sub).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _has_running_tasks(exclude_task_id: str | None = None) -> bool:
        """Return True if GlobalTaskManager reports running tasks.

        B-047: ``exclude_task_id`` ignoriert den eigenen Worker-Task —
        sonst sieht der UI-Worker sich selbst als "running" und blockiert
        den eigenen Service-Call.
        """
        try:
            from services.task_manager import GlobalTaskManager
            tm = GlobalTaskManager.instance()
            for t in tm.get_all_tasks():
                if t.status != "running":
                    continue
                if exclude_task_id is not None and getattr(t, "task_id", None) == exclude_task_id:
                    continue
                return True
            return False
        except (ImportError, AttributeError, RuntimeError):
            return False

    @staticmethod
    def _wait_for_tasks_idle(
        timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.2,
        exclude_task_id: str | None = None,
    ) -> bool:
        """B-136: Aktiv warten bis kein Task mehr running ist.

        B-047: ``exclude_task_id`` wird an _has_running_tasks weitergereicht.

        Returns:
            True wenn idle innerhalb der Timeout-Zeit erreicht wurde.
        """
        import time as _time
        deadline = _time.monotonic() + timeout_sec
        while _time.monotonic() < deadline:
            if not ProjectManager._has_running_tasks(exclude_task_id=exclude_task_id):
                return True
            _time.sleep(poll_interval_sec)
        return False

    @staticmethod
    def _validate_pb_studio_db(db_path: Path) -> None:
        """B-048: Validiert dass `db_path` eine echte PB-Studio-DB ist.

        Vor `set_project()` aufrufen — sonst überschreibt `init_db()`
        ggf. eine fremde Datei.

        Raises:
            FileNotFoundError: wenn die Datei nicht existiert
            ValueError: wenn das Schema nicht zu PB Studio gehört
        """
        if not db_path.exists():
            raise FileNotFoundError(f"DB-Datei nicht gefunden: {db_path}")
        if db_path.stat().st_size == 0:
            raise ValueError(
                f"Datei {db_path} ist leer — kein gültiges PB-Studio-Projekt."
            )
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='projects'"
                )
                if cursor.fetchone() is None:
                    raise ValueError(
                        f"Datei {db_path} hat keine 'projects'-Tabelle — "
                        "kein gültiges PB-Studio-Projekt."
                    )
        except sqlite3.DatabaseError as exc:
            raise ValueError(
                f"Datei {db_path} ist kein gültiges SQLite-File: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def create_project(self, path: Path, name: str,
                       resolution: str = "1920x1080",
                       fps: float = 30.0,
                       task_id: str | None = None) -> Path:
        """Create a new, empty project at *path*.

        *path* is the project folder (will be created).  A fresh
        ``pb_studio.db`` is written inside it together with the standard
        sub-directory tree.

        Returns the project folder path.

        Args:
            task_id: B-047 Cycle 13 — der aufrufende Worker reicht hier
                seine eigene task_id durch, damit ``_wait_for_tasks_idle``
                den eigenen Task aus dem running-Count exkludiert. Ohne
                das blockiert der eigene Worker sich selbst.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        FileExistsError
            If the target folder already contains a ``pb_studio.db``.
        """
        # B-136: Aktive Wartezeit statt single-shot TOCTOU-Check.
        # B-047 Cycle 13: exclude_task_id=task_id durchreichen.
        if not self._wait_for_tasks_idle(
            timeout_sec=10.0, exclude_task_id=task_id,
        ):
            raise RuntimeError(
                "Es laufen noch Hintergrund-Tasks. "
                "Bitte warte bis alle Tasks beendet sind."
            )

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        db_file = path / "pb_studio.db"
        if db_file.exists():
            raise FileExistsError(
                f"Im Ordner existiert bereits eine Projektdatei: {db_file}"
            )

        # Create directory structure
        self._ensure_dirs(path)

        # B-135 Fix: set_project erstellt jetzt selbst die Tabellen
        # unter _APP_ROOT_LOCK — der separate init_db() Call ist nicht
        # mehr noetig (er war ohnehin nicht atomar mit dem swap, was
        # ein Race-Window erzeugte). init_db() wird defensive trotzdem
        # gerufen falls der create_all in set_project gescheitert ist.
        import database
        database.set_project(path)
        database.init_db()  # idempotent — re-erstellt fehlende Tabellen

        # Write project metadata (via ORM — engine already points to new DB)
        from database import Project, engine
        from sqlalchemy.orm import Session as _Ses
        with _Ses(engine) as session:
            # Remove the auto-created "Default" project and insert ours
            for p in session.query(Project).filter(Project.deleted_at.is_(None)).all():
                session.delete(p)
            session.add(Project(
                name=name,
                path=str(path),
                resolution=resolution,
                fps=fps,
            ))
            try:
                session.commit()
            except Exception:  # broad catch intentional — SQLAlchemy commit can raise many error types
                session.rollback()
                raise

        logger.info("Neues Projekt erstellt: %s (%s, %s fps)", name, resolution, fps)
        self.project_changed.emit(path)
        return path

    def open_project(self, path: Path, task_id: str | None = None) -> dict:
        """Open an existing project at *path*.

        Validates that ``pb_studio.db`` exists, reads project meta via raw
        SQLite (not ORM — avoids import-order issues), swaps the DB engine,
        and emits ``project_changed``.

        Returns a dict with keys ``name``, ``resolution``, ``fps``.

        Args:
            task_id: B-047 Cycle 13 — siehe create_project.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        FileNotFoundError
            If ``pb_studio.db`` is missing in *path*.
        """
        # B-136: Aktive Wartezeit statt single-shot TOCTOU-Check.
        # B-047 Cycle 13: exclude_task_id=task_id durchreichen.
        if not self._wait_for_tasks_idle(
            timeout_sec=10.0, exclude_task_id=task_id,
        ):
            raise RuntimeError(
                "Es laufen noch Hintergrund-Tasks. "
                "Bitte warte bis alle Tasks beendet sind."
            )

        path = Path(path)
        db_file = path / "pb_studio.db"
        if not db_file.exists():
            raise FileNotFoundError(
                f"Keine Projektdatei gefunden: {db_file}"
            )

        # B-048: Schema-Validierung VOR Engine-Swap.
        # Ohne diesen Check würde init_db() eine leere oder fremde
        # Datei überschreiben (Datenverlust).
        self._validate_pb_studio_db(db_file)

        # Read project meta directly via sqlite3 (no ORM dependency)
        # H12-FIX: with-Statement statt manuelles conn.close() — verhindert Connection Leak bei Exception
        meta = {"name": path.name, "resolution": "1920x1080", "fps": 30.0}
        try:
            with sqlite3.connect(str(db_file)) as conn:
                row = conn.execute(
                    "SELECT name, resolution, fps FROM projects LIMIT 1"
                ).fetchone()
                if row:
                    meta["name"] = row[0] or path.name
                    meta["resolution"] = row[1] or "1920x1080"
                    meta["fps"] = row[2] or 30.0
        except (OSError, sqlite3.Error, ValueError) as exc:
            logger.warning("Projekt-Meta konnte nicht gelesen werden: %s", exc)

        # Ensure sub-directories exist (older projects might lack some)
        self._ensure_dirs(path)

        # Caches invalidieren bevor DB gewechselt wird (Stem-Audio, BPM, Video-Info etc.)
        try:
            from services.pacing_service import invalidate_pacing_caches
            invalidate_pacing_caches()
        except (ImportError, AttributeError, RuntimeError) as exc:
            logger.warning("Failed to invalidate pacing caches in open_project: %s", exc)

        # Swap database engine
        import database
        database.set_project(path)
        database.init_db()

        logger.info("Projekt geoeffnet: %s (%s)", meta["name"], path)
        self.project_changed.emit(path)
        return meta

    def save_project_as(self, target_path: Path, task_id: str | None = None) -> Path:
        """Copy the current project to *target_path*.

        Copies everything (DB + storage) to the new location, then opens
        the copy as the active project.

        Args:
            task_id: B-047 Cycle 13 — siehe create_project.

        Returns the new project folder path.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        """
        # B-136: Aktive Wartezeit statt single-shot TOCTOU-Check.
        # B-047 Cycle 13: exclude_task_id=task_id durchreichen.
        if not self._wait_for_tasks_idle(
            timeout_sec=10.0, exclude_task_id=task_id,
        ):
            raise RuntimeError(
                "Es laufen noch Hintergrund-Tasks. "
                "Bitte warte bis alle Tasks beendet sind."
            )

        import database.session as _session
        # Null-Check für APP_ROOT (B-001 Fix: database.session.APP_ROOT könnte None sein)
        if _session.APP_ROOT is None:
            raise RuntimeError(
                "Kein aktives Projekt geöffnet. APP_ROOT ist nicht initialisiert."
            )
        source = Path(_session.APP_ROOT)
        target_path = Path(target_path)

        if target_path.exists():
            raise FileExistsError(
                f"Zielordner existiert bereits: {target_path}"
            )

        logger.info("Kopiere Projekt: %s -> %s", source, target_path)

        # B-137 Fix: SQLite-safe hot-copy via Connection.backup() API.
        # shutil.copytree auf aktiver SQLite-DB riskiert WAL/SHM-mid-write
        # Inkonsistenz im Ziel. Connection.backup() ist transaktionssicher
        # auch waehrend andere Connections in die Source schreiben.
        target_path.mkdir(parents=True, exist_ok=False)
        try:
            self._copy_sqlite_db(source / "pb_studio.db",
                                  target_path / "pb_studio.db")
            for item in source.iterdir():
                if item.name == "pb_studio.db":
                    continue  # bereits per backup() kopiert
                if item.name.startswith("pb_studio.db-"):
                    # WAL/SHM/journal — regenerieren sich, nicht kopieren.
                    continue
                if item.is_dir():
                    shutil.copytree(item, target_path / item.name)
                else:
                    shutil.copy2(item, target_path / item.name)
        except Exception:
            # Bei Fehler angefangene Kopie aufraeumen, damit naechster
            # Save-As nicht auf "existiert bereits" stoesst.
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
            raise

        # Open the copy as the new active project
        self.open_project(target_path)
        logger.info("Projekt gespeichert unter: %s", target_path)
        return target_path

    @staticmethod
    def _copy_sqlite_db(src_db: Path, dst_db: Path) -> None:
        """B-137: SQLite hot-copy via Connection.backup() API.

        Transaktionssicher auch waehrend andere Connections (WAL-Writer)
        in die Source-DB schreiben.
        """
        src_conn = sqlite3.connect(str(src_db))
        try:
            dst_conn = sqlite3.connect(str(dst_db))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
