"""DaVinci-Style Workspace Navigation Bar."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal


class WorkspaceNavBar(QWidget):
    """Bottom navigation bar — DaVinci Resolve Style."""
    workspace_changed = Signal(int)

    WORKSPACE_NAMES = ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace_nav")
        self.setFixedHeight(42)

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

        for i, name in enumerate(self.WORKSPACE_NAMES):
            btn = QPushButton(name)
            btn.setObjectName("workspace_btn")
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(90)
            btn.setToolTip(tooltips[i])
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
