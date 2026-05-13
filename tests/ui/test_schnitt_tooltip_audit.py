import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QTreeWidget,
    QWidget,
)


def _qapp():
    return QApplication.instance() or QApplication([])


def test_enabled_schnitt_controls_have_tooltips_and_button_accessible_names():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace

    workspace = SchnittWorkspace()
    control_types = (QPushButton, QComboBox, QSlider, QSpinBox, QTreeWidget, QTextEdit)
    missing_tooltips = []
    missing_button_names = []

    for widget in workspace.findChildren(QWidget):
        if not isinstance(widget, control_types):
            continue
        if not widget.isEnabled():
            continue
        label = widget.objectName() or widget.__class__.__name__
        if not widget.toolTip().strip():
            missing_tooltips.append(label)
        if isinstance(widget, QPushButton) and not widget.accessibleName().strip():
            missing_button_names.append(label)

    assert missing_tooltips == []
    assert missing_button_names == []
