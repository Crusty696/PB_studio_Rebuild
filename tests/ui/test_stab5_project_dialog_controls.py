"""STAB-5 Controls #41-#47: NewProjectDialog/OpenProjectDialog elementgenau."""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_sqlite(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()


def _single_button(dialog: QDialog, text: str) -> QPushButton:
    buttons = [
        b for b in dialog.findChildren(QPushButton) if b.text() == text
    ]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dialog) is True
    assert button.isEnabled() is True
    return button


def test_new_project_browse_button_fills_path(monkeypatch, tmp_path) -> None:
    """Control #41: '...'-Button ruft Ordnerauswahl und setzt path_input."""
    app = _qapp()
    from ui.dialogs import project_dialog

    monkeypatch.setattr(
        project_dialog.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: str(tmp_path)),
    )
    dialog = project_dialog.NewProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "...")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.path_input.text() == str(tmp_path)
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_new_project_resolution_combo_feeds_get_values() -> None:
    """Control #42: resolution_combo-Auswahl landet in get_values()."""
    app = _qapp()
    from ui.dialogs.project_dialog import NewProjectDialog

    dialog = NewProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        combo = dialog.resolution_combo
        assert combo.isVisibleTo(dialog) is True
        assert combo.isEnabled() is True
        assert combo.count() == 6
        combo.setCurrentIndex(1)
        app.processEvents()
        assert dialog.get_values()["resolution"] == "3840x2160"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_new_project_cancel_button_rejects() -> None:
    """Control #43: 'Abbrechen' rejected den Dialog."""
    app = _qapp()
    from ui.dialogs.project_dialog import NewProjectDialog

    dialog = NewProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "Abbrechen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_new_project_ok_button_validates_then_accepts(
    monkeypatch, tmp_path
) -> None:
    """Control #44: 'Erstellen' warnt bei leerem Namen und akzeptiert
    erst mit Name + Pfad."""
    app = _qapp()
    from ui.dialogs import project_dialog

    warnings: list[str] = []
    monkeypatch.setattr(
        project_dialog.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **kw: warnings.append(text)),
    )
    dialog = project_dialog.NewProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "Erstellen")

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert warnings == ["Bitte einen Projektnamen eingeben."]
        assert dialog.isVisible() is True

        dialog.name_input.setText("Testprojekt")
        dialog.path_input.setText(str(tmp_path))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
        values = dialog.get_values()
        assert values["name"] == "Testprojekt"
        assert values["path"].name == "Testprojekt"
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_open_project_browse_button_fills_path_and_checks_db(
    monkeypatch, tmp_path
) -> None:
    """Control #45: '...'-Button setzt Pfad und validiert pb_studio.db."""
    app = _qapp()
    from ui.dialogs import project_dialog

    db = tmp_path / "pb_studio.db"
    _write_sqlite(db)
    monkeypatch.setattr(
        project_dialog.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: str(tmp_path)),
    )
    dialog = project_dialog.OpenProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "...")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.path_input.text() == str(tmp_path)
        assert dialog.status_label.text() == "pb_studio.db (SQLite) gefunden"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_open_project_cancel_button_rejects() -> None:
    """Control #46: 'Abbrechen' rejected den Dialog."""
    app = _qapp()
    from ui.dialogs.project_dialog import OpenProjectDialog

    dialog = OpenProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "Abbrechen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_open_project_ok_button_rejects_non_sqlite_then_accepts(
    monkeypatch, tmp_path
) -> None:
    """Control #47: 'Oeffnen' warnt bei ungueltiger DB und akzeptiert
    nur echte SQLite-Datei."""
    app = _qapp()
    from ui.dialogs import project_dialog

    warnings: list[str] = []
    monkeypatch.setattr(
        project_dialog.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **kw: warnings.append(text)),
    )
    db = tmp_path / "pb_studio.db"
    db.write_text("kein sqlite", encoding="utf-8")
    dialog = project_dialog.OpenProjectDialog()
    try:
        dialog.show()
        app.processEvents()
        dialog.path_input.setText(str(tmp_path))
        button = _single_button(dialog, "Oeffnen")

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(warnings) == 1
        assert "keine gueltige SQLite-Datenbank" in warnings[0]
        assert dialog.isVisible() is True

        db.unlink()
        _write_sqlite(db)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(warnings) == 1
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
        assert dialog.get_path() == tmp_path
    finally:
        dialog.deleteLater()
        app.processEvents()
