"""DaVinci-Style Workspace Navigation Bar."""

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
        font-size: 10px;
        letter-spacing: 1.0px;
        padding: 1px 14px;
        min-height: 16px;
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
    """Bottom navigation bar — DaVinci Resolve Style."""
    workspace_changed = Signal(int)

    WORKSPACE_NAMES = ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace_nav")
        # P9-LAYOUT: kompakte Tab-Bar (vorher 42 px riesig), siehe LAYOUT_PLAN.md
        self.setFixedHeight(20)
        self.setStyleSheet(_NAV_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addStretch()

        self._buttons: list[QPushButton] = []
        self._current_index = 0

        tooltips = [
            "MEDIA: Dateien importieren, verwalten und analysieren",
            "EDIT: Timeline bearbeiten, Clips schneiden, KI-Pacing",
            "STEMS: DAW-Ansicht mit 4 Stem-Wellenformen (Vocals, Drums, Bass, Other)",
            "CONVERT: Videos standardisieren (Aufloesung, FPS, Format)",
            "DELIVER: Finales Video exportieren und rendern",
        ]

        accessible_names = [
            "MEDIA Workspace",
            "EDIT Workspace",
            "STEMS Workspace",
            "CONVERT Workspace",
            "DELIVER Workspace",
        ]
        status_tips = [
            "MEDIA: Dateien importieren, verwalten und analysieren",
            "EDIT: Timeline bearbeiten, Clips schneiden, KI-Pacing",
            "STEMS: DAW-Ansicht mit 4 Stem-Wellenformen",
            "CONVERT: Videos standardisieren (Aufloesung, FPS, Format)",
            "DELIVER: Finales Video exportieren und rendern",
        ]

        for i, name in enumerate(self.WORKSPACE_NAMES):
            btn = QPushButton(name)
            btn.setObjectName("workspace_btn")
            btn.setCheckable(True)
            # P9-LAYOUT: kompakte Tab-Buttons (vorher 36 px hoch)
            btn.setFixedHeight(18)
            btn.setMinimumWidth(80)
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
