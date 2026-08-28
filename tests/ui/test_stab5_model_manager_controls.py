"""STAB-5 Controls #32-#40: ModelManagerDialog-Buttons elementgenau belegen.

Alle Klicks laufen offscreen ohne echte Threads/Netz/Disk:
- _start_scan wird IMMER klassen-seitig gepatcht, bevor __init__ laeuft
  (deckt QTimer.singleShot(100, ...) UND die _refresh_btn-Connection ab).
- Bound-Method-Connections (#32 _start_scan, #37 _on_cleanup_scan) muessen
  auf der KLASSE vor Instanziierung gepatcht werden; Lambda-/Body-Lookups
  (#33-#36, #39, #40) reichen als Instanz-Patch nach Konstruktion.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(dialog, root, text: str) -> QPushButton:
    """Genau EIN sichtbarer, aktiver Button mit diesem Text unterhalb von root."""
    buttons = [b for b in root.findChildren(QPushButton) if b.text() == text]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dialog) is True
    assert button.isEnabled() is True
    return button


def _single_button_by_tooltip(dialog, root, text: str, tooltip_part: str) -> QPushButton:
    """Disambiguierung fuer die zwei 'Herunterladen'-Buttons (Ollama vs. HF)."""
    buttons = [
        b for b in root.findChildren(QPushButton)
        if b.text() == text and tooltip_part in b.toolTip()
    ]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dialog) is True
    assert button.isEnabled() is True
    return button


class _FakeEntry:
    """Minimales ModelEntry-Duck-Type fuer die Populate-Methoden."""

    def __init__(self, model_id: str = "fake:model", source: str = "ollama"):
        self.model_id = model_id
        self.source = source
        self.display_name = model_id  # Service-Invariante: display_name == model_id
        self.size_mb = 100.0
        self.size_display = "100 MB"
        self.status = "installed"
        self.last_used_display = "vor 99 Tagen"
        self.days_since_used = 99


def _make_dialog(monkeypatch, scan_calls: list | None = None):
    """Dialog sicher bauen: _start_scan KLASSEN-seitig stubben BEVOR __init__
    laeuft — sonst startet QTimer.singleShot(100, self._start_scan) bei einem
    spaeteren processEvents() einen echten _ScanWorker-QThread (Netz)."""
    from ui.dialogs.model_manager_dialog import ModelManagerDialog

    calls = scan_calls if scan_calls is not None else []
    monkeypatch.setattr(
        ModelManagerDialog, "_start_scan", lambda self: calls.append("scan")
    )
    dlg = ModelManagerDialog(parent=None, ollama_url="http://localhost:1")
    dlg.show()
    QApplication.processEvents()
    return dlg


def _teardown(dlg):
    dlg.close()
    dlg.deleteLater()
    _qapp().processEvents()


def test_32_refresh_button_triggers_start_scan(monkeypatch) -> None:
    """Control #32: '⟳ Aktualisieren' -> _start_scan."""
    app = _qapp()
    scan_calls: list = []
    dlg = _make_dialog(monkeypatch, scan_calls)
    try:
        button = _single_button(dlg, dlg, "⟳ Aktualisieren")
        assert button is dlg._refresh_btn
        scan_calls.clear()  # evtl. bereits gefeuerter Init-Timer zaehlt nicht
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert scan_calls == ["scan"]
    finally:
        _teardown(dlg)


def test_33_installed_table_delete_button_calls_on_delete_model(monkeypatch) -> None:
    """Control #33: 'Löschen' in _populate_installed_table -> _on_delete_model."""
    app = _qapp()
    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(0)
        dlg._populate_installed_table([_FakeEntry("fake:model", "ollama")])
        app.processEvents()
        assert dlg._installed_table.rowCount() == 1
        recorded: list = []
        monkeypatch.setattr(
            dlg, "_on_delete_model", lambda m, s: recorded.append((m, s))
        )
        button = _single_button(dlg, dlg._installed_table, "Löschen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == [("fake:model", "ollama")]
    finally:
        _teardown(dlg)


def test_34_custom_ollama_pull_button_starts_download(monkeypatch) -> None:
    """Control #34: 'Herunterladen' (Ollama) -> _on_custom_ollama_pull."""
    app = _qapp()
    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(1)
        app.processEvents()
        recorded: list = []
        monkeypatch.setattr(
            dlg, "_start_download", lambda mid, src: recorded.append((mid, src))
        )
        dlg._custom_ollama_input.setText("llama3:latest")
        button = _single_button_by_tooltip(
            dlg, dlg._download_tab, "Herunterladen", "ollama pull"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == [("llama3:latest", "ollama")]
    finally:
        _teardown(dlg)


def test_35_custom_hf_button_starts_download(monkeypatch) -> None:
    """Control #35: 'Herunterladen' (HF) -> _on_custom_hf_download."""
    app = _qapp()
    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(1)
        app.processEvents()
        recorded: list = []
        monkeypatch.setattr(
            dlg, "_start_download", lambda mid, src: recorded.append((mid, src))
        )
        dlg._custom_hf_input.setText("microsoft/phi-2")
        button = _single_button_by_tooltip(
            dlg, dlg._download_tab, "Herunterladen", "HuggingFace-Modell"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == [("microsoft/phi-2", "huggingface")]
    finally:
        _teardown(dlg)


def test_36_recommended_dl_button_triggers_pull(monkeypatch) -> None:
    """Control #36: '⬇ Herunterladen' in _populate_dl_tables -> _on_pull_ollama."""
    app = _qapp()
    import services.model_lifecycle_service as mls

    dlg = _make_dialog(monkeypatch)
    try:
        monkeypatch.setattr(
            mls,
            "RECOMMENDED_OLLAMA_MODELS",
            [{
                "id": "fake:rec",
                "display": "Fake Rec",
                "size_gb": 1.0,
                "description": "Testmodell",
            }],
        )
        monkeypatch.setattr(mls, "RECOMMENDED_HF_MODELS", [])
        dlg._entries = []  # nichts installiert -> Button statt '✓ Installiert'
        dlg._populate_dl_tables()
        dlg._tabs.setCurrentIndex(1)
        app.processEvents()
        assert dlg._ollama_dl_table.rowCount() == 1

        recorded: list = []
        monkeypatch.setattr(dlg, "_on_pull_ollama", lambda mid: recorded.append(mid))
        # findChildren wuerde noch deleteLater-pendente Buttons der
        # Erst-Population sehen — deshalb direkt das aktuelle Zell-Widget.
        action_w = dlg._ollama_dl_table.cellWidget(0, 3)
        assert action_w is not None
        button = _single_button(dlg, action_w, "⬇ Herunterladen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == ["fake:rec"]
    finally:
        _teardown(dlg)


def test_37_cleanup_scan_button_triggers_on_cleanup_scan(monkeypatch) -> None:
    """Control #37: 'Analyse starten' -> _on_cleanup_scan (Klassen-Patch)."""
    app = _qapp()
    from ui.dialogs.model_manager_dialog import ModelManagerDialog

    recorded: list = []
    monkeypatch.setattr(
        ModelManagerDialog, "_on_cleanup_scan", lambda self: recorded.append("cleanup")
    )
    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(2)
        app.processEvents()
        button = _single_button(dlg, dlg._cleanup_tab, "Analyse starten")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == ["cleanup"]
    finally:
        _teardown(dlg)


def test_38_delete_all_button_confirms_and_starts_delete(monkeypatch) -> None:
    """Control #38: 'Alle ausgewählten löschen' -> Bestaetigung -> _start_delete."""
    app = _qapp()
    import ui.dialogs.model_manager_dialog as mm

    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(2)
        assert dlg._delete_all_btn.isEnabled() is False
        dlg._populate_cleanup_table([_FakeEntry("fake:model", "ollama")])
        app.processEvents()

        monkeypatch.setattr(
            mm.QMessageBox, "question", lambda *a, **k: mm.QMessageBox.Yes
        )
        recorded: list = []
        monkeypatch.setattr(dlg, "_start_delete", lambda targets: recorded.append(targets))

        button = _single_button(dlg, dlg._cleanup_tab, "Alle ausgewählten löschen")
        assert button is dlg._delete_all_btn
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        # Hinweis: Handler uebergibt name_item.text() == display_name als
        # model_id; Test nutzt display_name == model_id (Service-Invariante).
        assert recorded == [[("fake:model", "ollama")]]
    finally:
        _teardown(dlg)


def test_38b_delete_all_button_no_delete_when_declined(monkeypatch) -> None:
    """#38 Negativpfad: QMessageBox No -> _start_delete wird NICHT gerufen."""
    app = _qapp()
    import ui.dialogs.model_manager_dialog as mm

    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(2)
        dlg._populate_cleanup_table([_FakeEntry("fake:model", "ollama")])
        monkeypatch.setattr(
            mm.QMessageBox, "question", lambda *a, **k: mm.QMessageBox.No
        )
        recorded: list = []
        monkeypatch.setattr(dlg, "_start_delete", lambda targets: recorded.append(targets))
        QTest.mouseClick(dlg._delete_all_btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == []
    finally:
        _teardown(dlg)


def test_39_cleanup_table_delete_button_calls_on_delete_model(monkeypatch) -> None:
    """Control #39: 'Löschen' in _populate_cleanup_table -> _on_delete_model."""
    app = _qapp()
    dlg = _make_dialog(monkeypatch)
    try:
        dlg._tabs.setCurrentIndex(2)
        dlg._populate_cleanup_table([_FakeEntry("fake:model", "huggingface")])
        app.processEvents()
        assert dlg._cleanup_table.rowCount() == 1
        recorded: list = []
        monkeypatch.setattr(
            dlg, "_on_delete_model", lambda m, s: recorded.append((m, s))
        )
        button = _single_button(dlg, dlg._cleanup_table, "Löschen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert recorded == [("fake:model", "huggingface")]
    finally:
        _teardown(dlg)


def test_40_progress_row_cancel_button_cancels_download(monkeypatch) -> None:
    """Control #40: '✗' in _add_progress_row -> _on_cancel_download."""
    app = _qapp()
    import services.model_lifecycle_service as mls

    class _FakeSvc:
        def __init__(self):
            self.cancelled: list = []

        def cancel_download(self, model_id: str) -> None:
            self.cancelled.append(model_id)

    fake_svc = _FakeSvc()
    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda url: fake_svc)

    dlg = _make_dialog(monkeypatch)
    try:
        frame = dlg._add_progress_row("test:model")
        app.processEvents()
        assert dlg._tabs.currentIndex() == 1
        assert frame.property("model_id") == "test:model"

        button = _single_button(dlg, frame, "✗")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert fake_svc.cancelled == ["test:model"]
        assert dlg._status_lbl.text() == "Download 'test:model' abgebrochen."
    finally:
        _teardown(dlg)
