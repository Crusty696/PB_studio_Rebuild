"""
PB Studio — Centralized JSON Settings Store.

Replaces QSettings with a standard JSON-based configuration file.
Supports automatic migration from legacy QSettings storage.

Settings file location:
  - Windows: %APPDATA%/PBStudio/settings.json
  - Linux/macOS: ~/.config/PBStudio/settings.json
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

# Legacy QSettings identifiers (for migration)
_LEGACY_ORG_PBSTUDIO = "PBStudio"
_LEGACY_ORG_PAPERCLIP = "Paperclip"
_LEGACY_APP = "PBStudio"


def _get_settings_path() -> Path:
    """Return the platform-appropriate path for settings.json."""
    import platform

    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Roaming" / "PBStudio"
    else:
        base = Path.home() / ".config" / "PBStudio"

    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


class SettingsStore:
    """Centralized JSON-based settings storage with QSettings migration support."""

    def __init__(self):
        self._path = _get_settings_path()
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()  # FIX H-14: Thread-safe access to _data
        self._load()

    def _load(self) -> None:
        """Load settings from JSON file, migrating from QSettings if needed."""
        with self._lock:
            if self._path.exists():
                try:
                    with open(self._path, 'r', encoding='utf-8') as f:
                        self._data = json.load(f)
                    logger.info("Settings loaded from %s", self._path)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to load settings from %s: %s", self._path, e)
                    self._data = {}
            else:
                logger.info("Settings file not found, checking for legacy QSettings data")
                self._migrate_from_qsettings()

    def _migrate_from_qsettings(self) -> None:
        """Migrate existing data from QSettings to JSON format."""
        migrated_any = False

        # Migrate Ollama settings
        qs_pbstudio = QSettings(_LEGACY_ORG_PBSTUDIO, _LEGACY_APP)
        if qs_pbstudio.contains("ollama/enabled"):
            self._data["ollama"] = {
                "enabled": qs_pbstudio.value("ollama/enabled", True, type=bool),
                "url": qs_pbstudio.value("ollama/url", "http://localhost:11434", type=str),
                "model": qs_pbstudio.value("ollama/model", "", type=str),
            }
            logger.info("Migrated Ollama settings from QSettings")
            migrated_any = True

        # Migrate keyboard shortcuts
        shortcuts = {}
        for key in qs_pbstudio.allKeys():
            if key.startswith("shortcuts/"):
                action_id = key.replace("shortcuts/", "")
                shortcuts[action_id] = qs_pbstudio.value(key, type=str)

        if shortcuts:
            self._data["shortcuts"] = shortcuts
            logger.info("Migrated %d keyboard shortcuts from QSettings", len(shortcuts))
            migrated_any = True

        # Migrate recent projects (from Paperclip organization)
        qs_paperclip = QSettings(_LEGACY_ORG_PAPERCLIP, _LEGACY_APP)
        if qs_paperclip.contains("recentProjects"):
            raw = qs_paperclip.value("recentProjects", defaultValue=[])
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, list):
                raw = list(raw)
            # Filter to valid paths during migration
            valid = [p for p in raw if isinstance(p, str) and Path(p).exists()]
            if valid:
                self._data["recentProjects"] = valid
                logger.info("Migrated %d recent projects from QSettings", len(valid))
                migrated_any = True

        if migrated_any:
            self._save()
            logger.info("Migration complete, settings saved to %s", self._path)
        else:
            logger.info("No legacy settings found to migrate")

    def _save(self) -> None:
        """Persist current settings to JSON file."""
        with self._lock:
            try:
                with open(self._path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                logger.debug("Settings saved to %s", self._path)
            except OSError as e:
                logger.error("Failed to save settings to %s: %s", self._path, e)

    # ------------------------------------------------------------------
    # Generic access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level setting value."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a top-level setting value and persist."""
        with self._lock:
            self._data[key] = value
        self._save()

    def get_nested(self, *path: str, default: Any = None) -> Any:
        """Get a nested setting value (e.g., get_nested('ollama', 'enabled'))."""
        with self._lock:
            current = self._data
            for key in path:
                if not isinstance(current, dict):
                    return default
                current = current.get(key)
                if current is None:
                    return default
            return current

    def set_nested(self, *path: str, value: Any) -> None:
        """Set a nested setting value and persist (e.g., set_nested('ollama', 'enabled', value=True))."""
        if not path:
            return

        with self._lock:
            current = self._data
            for key in path[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            current[path[-1]] = value
        self._save()

    def get_section(self, section: str) -> dict[str, Any]:
        """Get an entire settings section as a dict."""
        with self._lock:
            return self._data.get(section, {})

    def set_section(self, section: str, data: dict[str, Any]) -> None:
        """Set an entire settings section and persist."""
        with self._lock:
            self._data[section] = data
        self._save()

    # ------------------------------------------------------------------
    # Convenience methods for specific settings
    # ------------------------------------------------------------------

    def get_ollama_settings(self) -> dict[str, Any]:
        """Get Ollama configuration."""
        return {
            "enabled": self.get_nested("ollama", "enabled", default=True),
            "url": self.get_nested("ollama", "url", default="http://localhost:11434"),
            "model": self.get_nested("ollama", "model", default=""),
        }

    def save_ollama_settings(self, enabled: bool, url: str, model: str) -> None:
        """Save Ollama configuration."""
        with self._lock:
            self._data["ollama"] = {
                "enabled": enabled,
                "url": url,
                "model": model,
            }
        self._save()

    def get_shortcut(self, action_id: str, default: str = "") -> str:
        """Get a keyboard shortcut sequence."""
        with self._lock:
            shortcuts = self._data.get("shortcuts", {})
            return shortcuts.get(action_id, default)

    def set_shortcut(self, action_id: str, sequence: str) -> None:
        """Set a keyboard shortcut sequence."""
        with self._lock:
            if "shortcuts" not in self._data:
                self._data["shortcuts"] = {}
            self._data["shortcuts"][action_id] = sequence
        self._save()

    def get_all_shortcuts(self) -> dict[str, str]:
        """Get all keyboard shortcuts."""
        with self._lock:
            return self._data.get("shortcuts", {})

    def set_all_shortcuts(self, shortcuts: dict[str, str]) -> None:
        """Set all keyboard shortcuts at once."""
        with self._lock:
            self._data["shortcuts"] = shortcuts
        self._save()

    def get_recent_projects(self) -> list[str]:
        """Get list of recent project paths."""
        with self._lock:
            return self._data.get("recentProjects", [])

    def set_recent_projects(self, projects: list[str]) -> None:
        """Set list of recent project paths."""
        with self._lock:
            self._data["recentProjects"] = projects
        self._save()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    """Get the global settings store instance."""
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store


def get_ollama_settings() -> dict[str, Any]:
    """Get Ollama configuration (convenience module-level wrapper)."""
    return get_settings_store().get_ollama_settings()

