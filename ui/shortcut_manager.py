"""
PB Studio — Keyboard Shortcut Manager (AUD-71).

Provides configurable key mappings persisted via QSettings.
Usage:
    from ui.shortcut_manager import get_shortcut_manager
    sm = get_shortcut_manager()
    if sm.matches("play_pause", key_event): ...
"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence

_SETTINGS_ORG = "PBStudio"
_SETTINGS_APP = "PBStudio"
_PREFIX = "shortcuts/"


# fmt: off
# Action ID → (display_name, description, default_key_sequence_string)
ACTIONS: dict[str, tuple[str, str, str]] = {
    "play_pause":    ("Play / Pause",       "Toggle playback",                  "Space"),
    "stop":          ("Stop",               "Stop playback / deselect all",     "Escape"),
    "shuttle_back":  ("Shuttle Backward",   "Slow-reverse / fast-rewind (J/K/L)","J"),
    "shuttle_pause": ("Shuttle Pause",      "Pause JKL shuttle",                "K"),
    "shuttle_fwd":   ("Shuttle Forward",    "Slow-fwd / fast-fwd (J/K/L)",      "L"),
    "set_in":        ("Set In-Point",       "Set in-point at current playhead", "I"),
    "set_out":       ("Set Out-Point",      "Set out-point at current playhead","O"),
    "set_anchor":    ("Set Anchor",         "Set anchor on selected clip",      "M"),
    "delete_clip":   ("Delete",             "Delete selected clips",            "Del"),
    "jump_start":    ("Jump to Start",      "Jump to timeline start",           "Home"),
    "jump_end":      ("Jump to End",        "Jump to timeline end",             "End"),
    "frame_back":    ("Frame Back",         "Step one frame backward",          "Left"),
    "frame_fwd":     ("Frame Forward",      "Step one frame forward",           "Right"),
    "zoom_in":       ("Zoom In",            "Zoom timeline in",                 "+"),
    "zoom_out":      ("Zoom Out",           "Zoom timeline out",                "-"),
    "undo":          ("Undo",               "Undo last action",                 "Ctrl+Z"),
    "redo":          ("Redo",               "Redo last action",                 "Ctrl+Y"),
    "copy":          ("Copy",               "Copy selected clips",              "Ctrl+C"),
    "paste":         ("Paste",              "Paste clips",                      "Ctrl+V"),
}
# fmt: on


def _event_int(event) -> int:
    """Return an int combining key + modifiers from a QKeyEvent."""
    return event.key() | int(event.modifiers())


class ShortcutManager:
    """Manages configurable keyboard shortcuts persisted via QSettings."""

    def __init__(self) -> None:
        self._sequences: dict[str, QKeySequence] = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load shortcuts from QSettings (falling back to defaults)."""
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        for action_id, (_name, _desc, default) in ACTIONS.items():
            stored = s.value(f"{_PREFIX}{action_id}", default, type=str)
            seq = QKeySequence(stored)
            self._sequences[action_id] = seq if not seq.isEmpty() else QKeySequence(default)

    def save(self) -> None:
        """Persist current shortcuts to QSettings."""
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        for action_id, seq in self._sequences.items():
            s.setValue(f"{_PREFIX}{action_id}", seq.toString())
        s.sync()

    def reset_to_defaults(self) -> None:
        """Reset all shortcuts to their factory defaults."""
        for action_id, (_name, _desc, default) in ACTIONS.items():
            self._sequences[action_id] = QKeySequence(default)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get_sequence(self, action_id: str) -> QKeySequence:
        return self._sequences.get(action_id, QKeySequence())

    def set_sequence(self, action_id: str, seq: QKeySequence) -> None:
        self._sequences[action_id] = seq

    def matches(self, action_id: str, event) -> bool:
        """Return True if the QKeyEvent matches the action's shortcut."""
        seq = self._sequences.get(action_id)
        if not seq or seq.isEmpty():
            return False
        return QKeySequence(_event_int(event)) == seq

    def display_text(self, action_id: str) -> str:
        """Human-readable key text for display in UI."""
        seq = self._sequences.get(action_id)
        return seq.toString() if seq else ""


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_manager: ShortcutManager | None = None


def get_shortcut_manager() -> ShortcutManager:
    global _manager
    if _manager is None:
        _manager = ShortcutManager()
    return _manager
