"""STEMS Workspace: DAW-style stem view with transport controls.

This is a thin wrapper — the actual StemWorkspace widget is in ui/widgets/stem_workspace.py.
Signal wiring to StemPlayer is done by PBWindow after construction.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from ui.widgets.stem_workspace import StemWorkspace as StemWorkspaceWidget


class StemsWorkspace(QWidget):
    """STEMS workspace container — wraps StemWorkspaceWidget.

    Attributes:
        stem_widget: The actual StemWorkspace with tracks, transport, waveforms.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stem_widget = StemWorkspaceWidget()
        layout.addWidget(self.stem_widget)
