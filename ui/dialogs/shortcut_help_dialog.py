"""Keyboard Shortcut Help Overlay — AUD-105.

Opens with Ctrl+? or F1. Shows all shortcuts grouped by context.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout,
)
from PySide6.QtCore import Qt

from ui.theme import (
    BG0, BG1, BG2, BG3, BG4,
    ACCENT, ACCENT_BRIGHT, ACCENT_MUTED,
    T1, T2, T4,
)


# ---------------------------------------------------------------------------
# Shortcut groups — (action_name, key_text)
# Keys that come from ShortcutManager are looked up dynamically at open time;
# hard-coded global shortcuts are defined here.
# ---------------------------------------------------------------------------

GLOBAL_SHORTCUTS: list[tuple[str, str]] = [
    ("MEDIA Workspace",          "1"),
    ("EDIT Workspace",           "2"),
    ("STEMS Workspace",          "3"),
    ("CONVERT Workspace",        "4"),
    ("DELIVER Workspace",        "5"),
    ("Neues Projekt",            "Ctrl+N"),
    ("Projekt öffnen",           "Ctrl+O"),
    ("Projekt speichern",        "Ctrl+S"),
    ("Einstellungen",            "Ctrl+,"),
    ("Hilfe (dieser Dialog)",    "F1 / Ctrl+?"),
    ("App beenden",              "Alt+F4"),
]

# These action IDs are looked up from ShortcutManager at runtime
TIMELINE_ACTION_IDS: list[str] = [
    "play_pause",
    "stop",
    "shuttle_back",
    "shuttle_pause",
    "shuttle_fwd",
    "set_in",
    "set_out",
    "set_anchor",
    "delete_clip",
    "jump_start",
    "jump_end",
    "frame_back",
    "frame_fwd",
    "zoom_in",
    "zoom_out",
    "undo",
    "redo",
    "copy",
    "paste",
]

STEM_SHORTCUTS: list[tuple[str, str]] = [
    ("Stem-Spur stummschalten",  "M"),
    ("Stem-Spur solo",           "S"),
    ("Alle Spuren zurücksetzen", "R"),
    ("Lautstärke +",             "Ctrl+Up"),
    ("Lautstärke −",             "Ctrl+Down"),
]


def _section_header(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color: {ACCENT}; font-size: 10px; font-weight: 700;"
        "letter-spacing: 1.5px; background: transparent;"
        f"border-bottom: 1px solid {ACCENT_MUTED}; padding-bottom: 4px;"
    )
    return lbl


def _key_badge(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"background: {BG3}; color: {T1};"
        f"border: 1px solid rgba(255,255,255,18);"
        "border-radius: 4px; padding: 2px 7px;"
        "font-family: 'Consolas', monospace; font-size: 11px; font-weight: 600;"
    )
    lbl.setFixedHeight(22)
    return lbl


def _action_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {T2}; background: transparent; font-size: 12px;")
    return lbl


def _build_shortcut_grid(rows: list[tuple[str, str]], parent: QWidget) -> QGridLayout:
    grid = QGridLayout()
    grid.setContentsMargins(0, 6, 0, 10)
    grid.setVerticalSpacing(5)
    grid.setHorizontalSpacing(12)
    grid.setColumnStretch(0, 1)

    for i, (name, key) in enumerate(rows):
        grid.addWidget(_action_label(name), i, 0)
        grid.addWidget(_key_badge(key), i, 1, Qt.AlignmentFlag.AlignRight)

    return grid


class ShortcutHelpDialog(QDialog):
    """Modal overlay showing all keyboard shortcuts grouped by context."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tastaturkürzel — PB Studio")
        self.setMinimumSize(520, 580)
        self.resize(560, 640)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(f"background-color: {BG1};")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background: {BG0}; border-bottom: 1px solid {BG3};")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(20, 0, 16, 0)

        title = QLabel("Tastaturkürzel")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {T1}; background: transparent;"
        )
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        hint = QLabel("F1 oder Ctrl+? zum Schließen")
        hint.setStyleSheet(f"font-size: 11px; color: {T4}; background: transparent;")
        hdr_layout.addWidget(hint)

        outer.addWidget(header)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG1}; border: none; }}"
            f"QScrollBar:vertical {{ background: {BG2}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {BG4}; border-radius: 3px; }}"
        )
        outer.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet(f"background: {BG1};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        # ── Three column layout (Global | Timeline | Stems) ──
        cols = QHBoxLayout()
        cols.setSpacing(20)
        cols.setAlignment(Qt.AlignmentFlag.AlignTop)

        cols.addLayout(self._build_global_section(), stretch=1)
        cols.addLayout(self._build_timeline_section(), stretch=1)
        cols.addLayout(self._build_stems_section(), stretch=1)

        layout.addLayout(cols)
        layout.addStretch()

        # ── Footer ──
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet(
            f"background: {BG0}; border-top: 1px solid {BG3};"
        )
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(20, 0, 16, 0)

        tip = QLabel("Kürzel in Einstellungen → Tastaturbelegung anpassbar")
        tip.setStyleSheet(f"font-size: 11px; color: {T4}; background: transparent;")
        ft_layout.addWidget(tip, stretch=1)

        btn_close = QPushButton("Schließen")
        btn_close.setFixedSize(100, 32)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip(
            "Tastaturkuerzel-Hilfe schliessen. Alternativ Escape, F1 oder Ctrl+? druecken."
        )
        btn_close.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: {BG0}; border: none;"
            "border-radius: 6px; font-weight: 700; font-size: 12px; }"
            f"QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}"
        )
        btn_close.clicked.connect(self.accept)
        ft_layout.addWidget(btn_close)

        outer.addWidget(footer)

    def _build_global_section(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        col.addWidget(_section_header("Global"))
        col.addLayout(_build_shortcut_grid(GLOBAL_SHORTCUTS, self))
        return col

    def _build_timeline_section(self) -> QVBoxLayout:
        from ui.shortcut_manager import ACTIONS, get_shortcut_manager
        sm = get_shortcut_manager()

        rows: list[tuple[str, str]] = []
        for action_id in TIMELINE_ACTION_IDS:
            if action_id in ACTIONS:
                display_name, _desc, _default = ACTIONS[action_id]
                key_text = sm.display_text(action_id) or _default
                rows.append((display_name, key_text))

        col = QVBoxLayout()
        col.setSpacing(4)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        col.addWidget(_section_header("Timeline / Edit"))
        col.addLayout(_build_shortcut_grid(rows, self))
        return col

    def _build_stems_section(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        col.addWidget(_section_header("Stem Workspace"))
        col.addLayout(_build_shortcut_grid(STEM_SHORTCUTS, self))
        return col

    def keyPressEvent(self, event) -> None:
        """Close on Escape, F1, or Ctrl+?."""
        key = event.key()
        mods = event.modifiers()
        if (
            key == Qt.Key.Key_Escape
            or key == Qt.Key.Key_F1
            or (key == Qt.Key.Key_Question and mods & Qt.KeyboardModifier.ControlModifier)
            or (key == Qt.Key.Key_Slash and mods & Qt.KeyboardModifier.ControlModifier)
        ):
            self.accept()
            return
        super().keyPressEvent(event)
