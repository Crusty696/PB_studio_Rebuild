"""SchnittEditorView — finale Editor-Stage mit 4 Sub-Tabs + persistentem Inspector.
Sub-Tab-Inhalte werden in Phasen 05–08 ausimplementiert."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTabWidget, QVBoxLayout, QLabel,
)
from ui.clip_inspector import ClipInspectorPanel
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


class SchnittEditorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_editor")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self.tab_schnitt = SchnittTabSchnitt(self)
        self.sub_tabs.addTab(self.tab_schnitt, "Schnitt")
        self.tab_pacing_anker = SchnittTabPacingAnker(self)
        self.sub_tabs.addTab(self.tab_pacing_anker, "Pacing & Anker")
        self.tab_audio = SchnittTabAudio(self)
        self.sub_tabs.addTab(self.tab_audio, "Audio")
        self.sub_tabs.addTab(self._stub("Sub-Tab RL & Notes — Phase 08"), "RL & Notes")
        layout.addWidget(self.sub_tabs, stretch=3)

        self.inspector_panel = ClipInspectorPanel(self)
        layout.addWidget(self.inspector_panel, stretch=1)

    @staticmethod
    def _stub(text: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
        v.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        v.addStretch(1)
        return w
