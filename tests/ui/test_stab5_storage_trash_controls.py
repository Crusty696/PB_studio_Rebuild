"""STAB-5 Controls #71-#78: StorageBrowserDialog + TrashDialog elementgenau."""

from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(dialog: QDialog, text: str) -> QPushButton:
    buttons = [
        b for b in dialog.findChildren(QPushButton) if b.text() == text
    ]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dialog) is True
    assert button.isEnabled() is True
    return button


# ── StorageBrowserDialog (#71-#75) ────────────────────────────────────────


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _storage_dialog(monkeypatch, tmp_path, rows):
    """StorageBrowserDialog ohne echte DB: Service + Session isoliert."""
    from ui.dialogs import storage_browser_dialog as mod

    calls = {"list": [], "delete": []}

    class _FakeService:
        def __init__(self, session, storage_root=None):
            calls["storage_root"] = storage_root

        def list_sources(self, unused_only=False, older_than_days=None):
            calls["list"].append(
                {"unused_only": unused_only, "older_than_days": older_than_days}
            )
            return rows

        def delete_analysis_sources(self, source_hashes, delete_storage_dirs=False):
            calls["delete"].append(
                {
                    "hashes": list(source_hashes),
                    "delete_storage_dirs": delete_storage_dirs,
                }
            )
            from services.storage_provenance.storage_browser import (
                StorageDeleteResult,
            )

            return StorageDeleteResult(
                deleted_sources=len(source_hashes),
                deleted_jobs=len(source_hashes),
                deleted_artifacts=0,
                deleted_storage_dirs=0,
                freed_bytes=0,
            )

    monkeypatch.setattr(mod, "nullpool_session", lambda: _FakeSession())
    monkeypatch.setattr(mod, "StorageBrowserService", _FakeService)
    # Sicherheitsnetz: ein unerwarteter Fehlerpfad darf im offscreen-Test
    # niemals einen echten modalen critical-Dialog blockieren lassen.
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError(f"unerwarteter critical-Dialog: {a[2:]}")
            )
        ),
    )
    monkeypatch.setattr(
        mod.StorageBrowserDialog,
        "_resolve_storage_root",
        staticmethod(lambda: tmp_path),
    )
    dialog = mod.StorageBrowserDialog()
    dialog.show()
    QApplication.processEvents()
    return dialog, calls


def _storage_rows():
    from services.storage_provenance.storage_browser import StorageBrowserRow

    return [
        StorageBrowserRow(
            source_sha256="a" * 64,
            file_name="clip_a.mp4",
            projects_used_by="p1",
            project_count=1,
            stages_done=3,
            total_bytes=2048,
            last_used=datetime(2026, 8, 1, 12, 0),
        )
    ]


def test_storage_unused_only_checkbox_triggers_filtered_refresh(
    monkeypatch, tmp_path
) -> None:
    """Control #71: Checkbox 'nicht-genutzt in Projekten' refresht gefiltert."""
    app = _qapp()
    dialog, calls = _storage_dialog(monkeypatch, tmp_path, _storage_rows())
    try:
        box = dialog._unused_only
        assert box.isVisibleTo(dialog) is True
        assert box.isEnabled() is True
        assert calls["list"] == [{"unused_only": False, "older_than_days": None}]
        QTest.mouseClick(box, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert box.isChecked() is True
        assert calls["list"][-1] == {"unused_only": True, "older_than_days": None}
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_storage_refresh_button_reloads(monkeypatch, tmp_path) -> None:
    """Control #72: 'Aktualisieren' loest erneuten Service-Load aus."""
    app = _qapp()
    dialog, calls = _storage_dialog(monkeypatch, tmp_path, _storage_rows())
    try:
        button = _single_button(dialog, "Aktualisieren")
        before = len(calls["list"])
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(calls["list"]) == before + 1
        assert dialog._summary.text().startswith("1 Quellen")
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_storage_delete_files_checkbox_controls_physical_delete(
    monkeypatch, tmp_path
) -> None:
    """Control #73: 'Auch Speicherdateien loeschen' steuert
    delete_storage_dirs im Loeschaufruf (B-547-Vertrag)."""
    app = _qapp()
    dialog, calls = _storage_dialog(monkeypatch, tmp_path, _storage_rows())
    try:
        box = dialog._delete_files
        assert box.isVisibleTo(dialog) is True
        assert box.isEnabled() is True
        QTest.mouseClick(box, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert box.isChecked() is True

        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )
        infos: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda parent, title, text, *a, **kw: infos.append(text)),
        )
        dialog._delete_sources(["a" * 64])
        assert calls["delete"] == [
            {"hashes": ["a" * 64], "delete_storage_dirs": True}
        ]
        assert len(infos) == 1
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_storage_delete_selected_button_paths(monkeypatch, tmp_path) -> None:
    """Control #74: 'Ausgewaehlte loeschen' meldet leere Auswahl sichtbar
    und loescht ausgewaehlte Quelle nach Bestaetigung."""
    app = _qapp()
    dialog, calls = _storage_dialog(monkeypatch, tmp_path, _storage_rows())
    try:
        button = _single_button(dialog, "Ausgewaehlte loeschen")
        infos: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda parent, title, text, *a, **kw: infos.append(text)),
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert infos == ["Keine Zeile ausgewaehlt."]
        assert calls["delete"] == []

        dialog.table.selectRow(0)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert calls["delete"] == [
            {"hashes": ["a" * 64], "delete_storage_dirs": False}
        ]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_storage_row_delete_button_deletes_single_source(
    monkeypatch, tmp_path
) -> None:
    """Control #75: Zeilenbutton 'Analysen loeschen' loescht genau die
    Quelle der Zeile nach Bestaetigung."""
    app = _qapp()
    dialog, calls = _storage_dialog(monkeypatch, tmp_path, _storage_rows())
    try:
        row_btn = dialog.table.cellWidget(0, 6)
        assert isinstance(row_btn, QPushButton)
        assert row_btn.text() == "Analysen loeschen"
        assert row_btn.isEnabled() is True
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda *a, **kw: None),
        )
        QTest.mouseClick(row_btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert calls["delete"] == [
            {"hashes": ["a" * 64], "delete_storage_dirs": False}
        ]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


# ── TrashDialog (#76-#78) ────────────────────────────────────────────────


def _trash_dialog(monkeypatch, items):
    """TrashDialog ohne echte Worker-Threads: run_worker synchron gefaked."""
    from ui.dialogs import trash_dialog as mod

    calls = {"restore": [], "purge": []}

    def fake_run_worker(parent, worker, on_finish=None, on_error=None):
        if isinstance(worker, mod._TrashLoadWorker):
            on_finish(items)
        elif isinstance(worker, mod._TrashRestoreWorker):
            calls["restore"].append(
                (worker._video_ids, worker._audio_ids)
            )
            on_finish(len(worker._video_ids) + len(worker._audio_ids))
        elif isinstance(worker, mod._TrashPurgeWorker):
            calls["purge"].append(worker._project_id)
            on_finish(len(items))
        else:  # pragma: no cover - unexpected worker
            raise AssertionError(type(worker))

    monkeypatch.setattr(mod, "run_worker", fake_run_worker)
    dialog = mod.TrashDialog(project_id=7)
    dialog.show()
    QApplication.processEvents()
    return dialog, calls


_TRASH_ITEMS = [
    {"type": "Video", "id": 11, "title": "clip", "deleted_at": None},
    {"type": "Audio", "id": 22, "title": "track", "deleted_at": None},
]


def test_trash_restore_button_paths(monkeypatch) -> None:
    """Control #76: Restore meldet leere Auswahl sichtbar und stellt
    ausgewaehlte IDs wieder her."""
    app = _qapp()
    dialog, calls = _trash_dialog(monkeypatch, list(_TRASH_ITEMS))
    try:
        button = _single_button(dialog, "Ausgewaehlte wiederherstellen")
        infos: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda parent, title, text, *a, **kw: infos.append(text)),
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert infos == ["Bitte zuerst Zeilen auswaehlen."]
        assert calls["restore"] == []

        dialog.table.selectRow(0)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert calls["restore"] == [([11], [])]
        assert infos[-1] == "1 Medien wiederhergestellt."
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_trash_purge_button_requires_confirmation(monkeypatch) -> None:
    """Control #77: 'Papierkorb leeren' purged nur nach Yes-Bestaetigung."""
    app = _qapp()
    dialog, calls = _trash_dialog(monkeypatch, list(_TRASH_ITEMS))
    try:
        button = _single_button(dialog, "Papierkorb leeren")
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            staticmethod(lambda *a, **kw: QMessageBox.Cancel),
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert calls["purge"] == []

        monkeypatch.setattr(
            QMessageBox,
            "warning",
            staticmethod(lambda *a, **kw: QMessageBox.Yes),
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda *a, **kw: None),
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert calls["purge"] == [7]
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_trash_close_button_accepts(monkeypatch) -> None:
    """Control #78: 'Schliessen' akzeptiert und versteckt den Dialog."""
    app = _qapp()
    dialog, _calls = _trash_dialog(monkeypatch, [])
    try:
        button = _single_button(dialog, "Schliessen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()
