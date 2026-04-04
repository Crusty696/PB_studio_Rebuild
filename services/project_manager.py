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
    def _has_running_tasks() -> bool:
        """Return True if GlobalTaskManager reports running tasks."""
        try:
            from services.task_manager import GlobalTaskManager
            tm = GlobalTaskManager.instance()
            return any(t.status == "running" for t in tm.get_all_tasks())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def create_project(self, path: Path, name: str,
                       resolution: str = "1920x1080",
                       fps: float = 30.0) -> Path:
        """Create a new, empty project at *path*.

        *path* is the project folder (will be created).  A fresh
        ``pb_studio.db`` is written inside it together with the standard
        sub-directory tree.

        Returns the project folder path.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        FileExistsError
            If the target folder already contains a ``pb_studio.db``.
        """
        if self._has_running_tasks():
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

        # Swap the database engine to point at the new location
        import database
        database.set_project(path)
        database.init_db()

        # Write project metadata (via ORM — engine already points to new DB)
        from database import Project, Session, engine
        from sqlalchemy.orm import Session as _Ses
        with _Ses(engine) as session:
            # Remove the auto-created "Default" project and insert ours
            for p in session.query(Project).all():
                session.delete(p)
            session.add(Project(
                name=name,
                path=str(path),
                resolution=resolution,
                fps=fps,
            ))
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise

        logger.info("Neues Projekt erstellt: %s (%s, %s fps)", name, resolution, fps)
        self.project_changed.emit(path)
        return path

    def open_project(self, path: Path) -> dict:
        """Open an existing project at *path*.

        Validates that ``pb_studio.db`` exists, reads project meta via raw
        SQLite (not ORM — avoids import-order issues), swaps the DB engine,
        and emits ``project_changed``.

        Returns a dict with keys ``name``, ``resolution``, ``fps``.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        FileNotFoundError
            If ``pb_studio.db`` is missing in *path*.
        """
        if self._has_running_tasks():
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

        # Read project meta directly via sqlite3 (no ORM dependency)
        meta = {"name": path.name, "resolution": "1920x1080", "fps": 30.0}
        try:
            conn = sqlite3.connect(str(db_file))
            row = conn.execute(
                "SELECT name, resolution, fps FROM projects LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                meta["name"] = row[0] or path.name
                meta["resolution"] = row[1] or "1920x1080"
                meta["fps"] = row[2] or 30.0
        except Exception as exc:
            logger.warning("Projekt-Meta konnte nicht gelesen werden: %s", exc)

        # Ensure sub-directories exist (older projects might lack some)
        self._ensure_dirs(path)

        # Caches invalidieren bevor DB gewechselt wird (Stem-Audio, BPM, Video-Info etc.)
        try:
            from services.pacing_service import invalidate_pacing_caches
            invalidate_pacing_caches()
        except Exception as exc:
            logger.warning("Failed to invalidate pacing caches in open_project: %s", exc)

        # Swap database engine
        import database
        database.set_project(path)
        database.init_db()

        logger.info("Projekt geoeffnet: %s (%s)", meta["name"], path)
        self.project_changed.emit(path)
        return meta

    def save_project_as(self, target_path: Path) -> Path:
        """Copy the current project to *target_path*.

        Copies everything (DB + storage) to the new location, then opens
        the copy as the active project.

        Returns the new project folder path.

        Raises
        ------
        RuntimeError
            If background tasks are still running.
        """
        if self._has_running_tasks():
            raise RuntimeError(
                "Es laufen noch Hintergrund-Tasks. "
                "Bitte warte bis alle Tasks beendet sind."
            )

        import database
        # Null-Check für APP_ROOT (B-001 Fix: database.APP_ROOT könnte None sein)
        if database.APP_ROOT is None:
            raise RuntimeError(
                "Kein aktives Projekt geöffnet. APP_ROOT ist nicht initialisiert."
            )
        source = Path(database.APP_ROOT)
        target_path = Path(target_path)

        if target_path.exists():
            raise FileExistsError(
                f"Zielordner existiert bereits: {target_path}"
            )

        logger.info("Kopiere Projekt: %s -> %s", source, target_path)
        shutil.copytree(source, target_path)

        # Open the copy as the new active project
        meta = self.open_project(target_path)
        logger.info("Projekt gespeichert unter: %s", target_path)
        return target_path
