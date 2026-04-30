"""Workflow navigation for the PB Studio Director's Cockpit."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal

_NAV_STYLE = """
    QWidget#workspace_nav {
        background: #0a0d12;
        border-top: 1px solid rgba(255,255,255,0.05);
    }
    QPushButton#workspace_btn {
        background: transparent;
        color: #6b7280;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0px;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0px;
        padding: 3px 16px;
        min-height: 24px;
        text-transform: uppercase;
    }
    QPushButton#workspace_btn:hover {
        color: #9ca3af;
        background: rgba(255,255,255,0.03);
    }
    QPushButton#workspace_btn:checked {
        color: #f0c866;
        border-bottom: 2px solid #d4a44a;
        background: rgba(212, 164, 74, 0.08);
    }
"""


class WorkspaceNavBar(QWidget):
    """Workflow rail: shows the order PB Studio work actually follows."""
    workspace_changed = Signal(int)

    WORKSPACE_NAMES = [
        "PROJEKT",
        "QUELLEN",
        "ANALYSE",
        "AUTO-SCHNITT",
        "REVIEW",
        "EXPORT",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace_nav")
        self.setFixedHeight(34)
        self.setStyleSheet(_NAV_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addStretch()

        self._buttons: list[QPushButton] = []
        self._current_index = 0

        tooltips = [
            "Projekt: Projektstatus, letzte Projekte und naechster Schritt",
            "Quellen vorbereiten: Medien importieren, pruefen und standardisieren",
            "Analyse: Audio, Stems, Struktur, Video-Pipeline und Status",
            "Auto-Schnitt: Pacing einstellen und beat-synchronen Schnitt erzeugen",
            "Review: Timeline, Vorschau, Inspector und Anker pruefen",
            "Export: Preview und finales Video rendern",
        ]

        accessible_names = [
            "Projekt Workflow",
            "Quellen vorbereiten Workflow",
            "Analyse Workflow",
            "Auto-Schnitt Workflow",
            "Review Workflow",
            "Export Workflow",
        ]
        status_tips = [
            "Projektstatus und Startpunkt",
            "Medien importieren und vorbereiten",
            "Analyse- und Stem-Pipeline",
            "Pacing und Auto-Edit",
            "Timeline pruefen und korrigieren",
            "Finales Video exportieren",
        ]

        for i, name in enumerate(self.WORKSPACE_NAMES):
            btn = QPushButton(name)
            btn.setObjectName("workspace_btn")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(110)
            btn.setToolTip(tooltips[i])
            btn.setAccessibleName(accessible_names[i])
            btn.setStatusTip(status_tips[i])
            btn.clicked.connect(lambda checked, idx=i: self._on_click(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

        self._buttons[0].setChecked(True)

    def _on_click(self, index: int):
        self._current_index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self.workspace_changed.emit(index)

    def set_workspace(self, index: int):
        if 0 <= index < len(self._buttons):
            self._on_click(index)
