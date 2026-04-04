"""RecentProjectsManager — Persistiert die zuletzt geoeffneten Projekte.

Speichert bis zu MAX_ENTRIES Projekt-Pfade in QSettings (native Registry
auf Windows, ~/.config auf Linux/macOS).  Kein zusaetzlicher Datei-Overhead.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

_ORG = "Paperclip"
_APP = "PBStudio"
_KEY = "recentProjects"
MAX_ENTRIES = 10


class RecentProjectsManager:
    """Singleton-artiger Helfer fuer die Liste zuletzt geoeffneter Projekte."""

    _settings = QSettings(_ORG, _APP)

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
        cls._settings.setValue(_KEY, entries)
        cls._settings.sync()
        logger.debug("Recent projects updated: %s", entries)

    @classmethod
    def get_all(cls) -> list[str]:
        """Gibt die Liste aller gespeicherten Pfade zurueck (neueste zuerst).

        Pfade, die nicht mehr existieren, werden still herausgefiltert.
        """
        raw = cls._settings.value(_KEY, defaultValue=[])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = list(raw)
        # Filter missing paths
        valid: list[str] = []
        for p in raw:
            if isinstance(p, str) and Path(p).exists():
                valid.append(p)
        if len(valid) != len(raw):
            cls._settings.setValue(_KEY, valid)
            cls._settings.sync()
        return valid

    @classmethod
    def clear_entry(cls, path: Path | str) -> None:
        """Entfernt einen einzelnen Eintrag aus der Liste (z.B. nach FileNotFoundError)."""
        path_str = str(Path(path).resolve())
        entries = [e for e in cls.get_all() if e != path_str]
        cls._settings.setValue(_KEY, entries)
        cls._settings.sync()

    @classmethod
    def clear(cls) -> None:
        """Loescht die gesamte Liste."""
        cls._settings.remove(_KEY)
        cls._settings.sync()
