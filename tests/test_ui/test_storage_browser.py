from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from services.storage_provenance.storage_browser import StorageBrowserRow


def test_storage_browser_dialog_contract_present() -> None:
    source = Path("ui/dialogs/storage_browser_dialog.py").read_text(encoding="utf-8")

    assert "class StorageBrowserDialog" in source
    assert "Analysen loeschen" in source
    assert "Ausgewaehlte loeschen" in source
    assert "nicht-genutzt" in source
    assert "alt >" in source


def test_settings_dialog_exposes_storage_browser_button() -> None:
    source = Path("ui/dialogs/settings_dialog.py").read_text(encoding="utf-8")

    assert "Storage-Browser" in source
    assert "StorageBrowserDialog" in source


def test_storage_browser_dialog_populates_rows_and_selection(monkeypatch, qapp) -> None:
    from ui.dialogs import storage_browser_dialog as mod

    rows = [
        StorageBrowserRow(
            source_sha256="a" * 64,
            file_name="track.wav",
            projects_used_by="Projekt A",
            project_count=1,
            stages_done=2,
            total_bytes=2048,
            last_used=datetime(2026, 6, 15, 12, 0),
        )
    ]

    @contextmanager
    def fake_session():
        yield object()

    class FakeService:
        def __init__(self, session):
            self.session = session

        def list_sources(self, **kwargs):
            return rows

    monkeypatch.setattr(mod, "nullpool_session", fake_session)
    monkeypatch.setattr(mod, "StorageBrowserService", FakeService)

    dialog = mod.StorageBrowserDialog()
    dialog.table.selectRow(0)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "aaaaaaaaaaaa"
    assert dialog.table.item(0, 1).text() == "track.wav"
    assert dialog.table.item(0, 4).text() == "2.0 KB"
    assert dialog.table.item(0, 5).text() == "2026-06-15 12:00"
    assert dialog._summary.text() == "1 Quellen"
    assert dialog._selected_sources() == ["a" * 64]


def test_storage_browser_dialog_delete_paths(monkeypatch, qapp) -> None:
    from ui.dialogs import storage_browser_dialog as mod

    deleted: list[list[str]] = []
    info_messages: list[str] = []

    @contextmanager
    def fake_session():
        yield object()

    class FakeService:
        def __init__(self, session):
            self.session = session

        def list_sources(self, **kwargs):
            return []

        def delete_analysis_sources(self, source_hashes):
            deleted.append(list(source_hashes))
            return SimpleNamespace(deleted_jobs=3)

    monkeypatch.setattr(mod, "nullpool_session", fake_session)
    monkeypatch.setattr(mod, "StorageBrowserService", FakeService)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, text: info_messages.append(text))

    dialog = mod.StorageBrowserDialog()
    dialog._delete_sources([])
    dialog._delete_sources(["b" * 64])

    assert info_messages[0] == "Keine Zeile ausgewaehlt."
    assert deleted == [["b" * 64]]
    assert info_messages[-1] == "3 Analyse-Job(s) geloescht."
