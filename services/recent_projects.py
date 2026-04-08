"""RecentProjectsManager — Persistiert die zuletzt geoeffneten Projekte.

Speichert bis zu MAX_ENTRIES Projekt-Pfade in JSON settings.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.settings_store import get_settings_store

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10


class RecentProjectsManager:
    """Singleton-artiger Helfer fuer die Liste zuletzt geoeffneter Projekte."""

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @classmethod
    def add(cls, path: Path | str) -> None:
        """Fuege *path* an den Anfang der Liste ein (Duplikate werden entfernt)."""
        path_str = str(Path(path).resolve())
        entries = cls.get_all()
        # Remove existing entry (dedup)
        entries = [e for e in entries if e != path_str]
        entries.insert(0, path_str)
        entries = entries[:MAX_ENTRIES]
        get_settings_store().set_recent_projects(entries)
        logger.debug("Recent projects updated: %s", entries)

    @classmethod
    def get_all(cls) -> list[str]:
        """Gibt die Liste aller gespeicherten Pfade zurueck (neueste zuerst).

        Pfade, die nicht mehr existieren, werden still herausgefiltert.
        """
        raw = get_settings_store().get_recent_projects()
        # Filter missing paths
        valid: list[str] = []
        for p in raw:
            if isinstance(p, str) and Path(p).exists():
                valid.append(p)
        if len(valid) != len(raw):
            get_settings_store().set_recent_projects(valid)
        return valid

    @classmethod
    def clear_entry(cls, path: Path | str) -> None:
        """Entfernt einen einzelnen Eintrag aus der Liste (z.B. nach FileNotFoundError)."""
        path_str = str(Path(path).resolve())
        entries = [e for e in cls.get_all() if e != path_str]
        get_settings_store().set_recent_projects(entries)

    @classmethod
    def clear(cls) -> None:
        """Loescht die gesamte Liste."""
        get_settings_store().set_recent_projects([])
