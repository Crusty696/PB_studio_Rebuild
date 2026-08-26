from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QTreeWidget,
)

import ui.controllers.edit_workspace as edit_workspace_module
from ui.controllers.edit_workspace import EditWorkspaceController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Rows:
    def all(self) -> list[object]:
        return []


class _Session:
    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *args) -> None:
        pass

    def execute(self, _statement) -> _Rows:
        return _Rows()


def test_scene_combo_selection_reaches_anchor_item(monkeypatch) -> None:
    _qapp()
    monkeypatch.setattr(
        edit_workspace_module, "DBSession", lambda _engine: _Session()
    )

    def _accept_with_scene(dialog: QDialog) -> QDialog.DialogCode:
        scene_combo = dialog.findChild(QComboBox)
        time_spin = dialog.findChild(QDoubleSpinBox)
        add_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Hinzufuegen"
        )
        assert scene_combo is not None
        assert time_spin is not None
        assert add_button.isEnabled() is False
        scene_combo.addItem("Kontrollclip | Szene 42 (1.0-2.0s)", "scene-42")
        scene_combo.setCurrentIndex(1)
        assert add_button.isEnabled() is True
        scene_combo.setCurrentIndex(0)
        assert add_button.isEnabled() is False
        scene_combo.setCurrentIndex(1)
        assert add_button.isEnabled() is True
        time_spin.setValue(12.5)
        add_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        return QDialog.DialogCode(dialog.result())

    monkeypatch.setattr(QDialog, "exec", _accept_with_scene)
    anchor_list = QTreeWidget()
    console = QTextEdit()
    window = QMainWindow()
    window.anchor_list = anchor_list
    window.console_text = console
    controller = EditWorkspaceController.__new__(EditWorkspaceController)
    controller.window = window

    try:
        controller._add_anchor_dialog()

        assert anchor_list.topLevelItemCount() == 1
        item = anchor_list.topLevelItem(0)
        assert item.data(0, Qt.ItemDataRole.UserRole) == "scene-42"
        assert "Szene 42" in item.text(1)
        assert controller._collect_anchors_from_ui() == [
            {"time": 12.5, "scene_id": "scene-42"}
        ]
        assert "[Anchor] Anker bei 0:12.50" in console.toPlainText()
    finally:
        window.close()
        window.deleteLater()


def test_placeholder_accept_does_not_create_anchor(monkeypatch) -> None:
    _qapp()
    monkeypatch.setattr(
        edit_workspace_module, "DBSession", lambda _engine: _Session()
    )
    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    anchor_list = QTreeWidget()
    console = QTextEdit()
    window = QMainWindow()
    window.anchor_list = anchor_list
    window.console_text = console
    controller = EditWorkspaceController.__new__(EditWorkspaceController)
    controller.window = window

    try:
        controller._add_anchor_dialog()

        assert anchor_list.topLevelItemCount() == 0
        assert controller._collect_anchors_from_ui() == []
    finally:
        window.close()
        window.deleteLater()
