import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QListWidget,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QTreeWidget,
    QWidget,
)


def _qapp():
    return QApplication.instance() or QApplication([])


def test_enabled_schnitt_controls_have_tooltips_and_button_accessible_names():
    _qapp()
    from ui.workspaces.schnitt_workspace import STATE_EDITOR, SchnittWorkspace

    workspace = SchnittWorkspace()
    workspace.resize(1280, 900)
    workspace._stack.setCurrentIndex(STATE_EDITOR)
    workspace.show()
    QApplication.processEvents()

    control_types = (
        QPushButton,
        QComboBox,
        QSlider,
        QSpinBox,
        QTreeWidget,
        QTextEdit,
        QTableWidget,
        QListWidget,
    )
    missing_tooltips = []
    missing_button_names = []

    sub_tabs = workspace.editor_view.sub_tabs
    for tab_index in range(sub_tabs.count()):
        tab_name = sub_tabs.tabText(tab_index)
        assert sub_tabs.tabToolTip(tab_index).strip(), f"{tab_name}: missing tab tooltip"
        sub_tabs.setCurrentIndex(tab_index)
        QApplication.processEvents()

        for widget in workspace.findChildren(QWidget):
            if not widget.isVisibleTo(workspace) or not widget.isEnabled():
                continue
            label = f"{tab_name}:{widget.objectName() or widget.__class__.__name__}"
            if isinstance(widget, control_types):
                if not widget.toolTip().strip():
                    missing_tooltips.append(label)
                if isinstance(widget, QPushButton) and not widget.accessibleName().strip():
                    missing_button_names.append(label)
            if isinstance(widget, QAbstractSpinBox):
                line_edit = widget.lineEdit()
                if line_edit is not None and not line_edit.toolTip().strip():
                    missing_tooltips.append(f"{tab_name}:{line_edit.objectName() or 'spinbox_lineedit'}")

    assert missing_tooltips == []
    assert missing_button_names == []
