"""STAB-5 Controls #57-#63: SetupWizard-Controls elementgenau belegen.

#57 QCheckBox Ollama-Modellzeile   (Factory _model_row)
#58 QCheckBox HF-Modellzeile — ACHTUNG: _HF_MODELS ist im Produkt leer ->
    Zeile zur Laufzeit toter Code; Beleg hier via monkeypatch (Finding B-920).
#59 _PageDownload._cancel_btn 'Abbrechen'
#60 SetupWizard._skip_btn 'Überspringen'
#61 SetupWizard._back_btn 'Zurück'
#62 SetupWizard._next_btn 'Weiter →'
#63 launch_btn 'App starten  →'

Isolation:
- QSettings auf Test-Organisation umgebogen (B-807-Muster) -> keine
  Host-Settings-Writes durch _skip/_launch/done().
- services.startup_checks.run_startup_checks gemockt -> kein Subprozess/HTTP.
- Kein echter Download/QThread: #59 nutzt Fake-Worker; #60-#63 betreten den
  Download-Startpfad (_page_dl.start) nie.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(root, text: str) -> QPushButton:
    buttons = [b for b in root.findChildren(QPushButton) if b.text() == text]
    assert len(buttons) == 1, f"Button {text!r} nicht eindeutig: {len(buttons)}x"
    button = buttons[0]
    assert button.isVisibleTo(root) is True
    assert button.isEnabled() is True
    return button


def _click_checkbox(cb: QCheckBox) -> None:
    # Textlose QCheckBox: deterministisch auf den Indikator klicken.
    QTest.mouseClick(cb, Qt.MouseButton.LeftButton, pos=QPoint(8, cb.height() // 2))


_FAKE_STATUS = SimpleNamespace(
    cuda_ok=True, gpu_name="GTX 1060", gpu_vram_mb=6144,
    ffmpeg_ok=True, ffmpeg_version="6.0", ffmpeg_path="ffmpeg",
    ffprobe_ok=True, ffprobe_path="ffprobe",
    nvenc_ok=True, nvenc_detail="",
    ollama_ok=True,
    hf_cache_ok=True, hf_cache_source="env", hf_cache_path="C:/hf",
    hf_cache_detail="",
    disk_ok=True, disk_free_gb=100.0,
    model_cache_warnings=[],
)


@pytest.fixture()
def wizard_env(monkeypatch):
    """Isolierte QSettings + gemockter System-Check (kein Subprozess/HTTP)."""
    import services.startup_checks as sc
    import ui.dialogs.setup_wizard as sw

    monkeypatch.setattr(sc, "run_startup_checks", lambda: _FAKE_STATUS)

    org, app_name = "PBStudioTest", "STAB5Wizard"
    monkeypatch.setattr(sw, "_SETTINGS_ORG", org)
    monkeypatch.setattr(sw, "_SETTINGS_APP", app_name)
    s = QSettings(org, app_name)
    s.remove(sw._SETUP_KEY)
    s.sync()
    yield sw
    s.remove(sw._SETUP_KEY)
    s.sync()


def _make_wizard(sw):
    wizard = sw.SetupWizard()
    wizard.show()
    QApplication.processEvents()
    assert wizard._stack.currentIndex() == sw.SetupWizard.PAGE_HARDWARE
    return wizard


def test_control_57_ollama_checkbox_toggles_and_updates_selection() -> None:
    """#57: Ollama-Checkbox klickbar, wirkt auf Auswahl + Groessensumme."""
    app = _qapp()
    from ui.dialogs.setup_wizard import _PageModels

    page = _PageModels()
    page.show()
    app.processEvents()
    try:
        assert len(page.findChildren(QCheckBox)) == 2
        gemma = page._checkboxes["gemma3:4b"]
        phi = page._checkboxes["phi3:mini"]
        for cb in (gemma, phi):
            assert cb.isVisibleTo(page) is True
            assert cb.isEnabled() is True
        assert gemma.isChecked() is True
        assert phi.isChecked() is False
        assert "3.3 GB" in page._size_lbl.text()
        assert page.selected_ollama() == ["gemma3:4b"]

        _click_checkbox(phi)
        app.processEvents()

        assert phi.isChecked() is True
        assert page.selected_ollama() == ["gemma3:4b", "phi3:mini"]
        assert "5.6 GB" in page._size_lbl.text()
    finally:
        page.deleteLater()
        app.processEvents()


def test_control_58_hf_checkbox_via_factory(monkeypatch) -> None:
    """#58: HF-Checkbox. _HF_MODELS ist im Produkt leer -> Control nur via
    Monkeypatch erreichbar (Finding B-920)."""
    app = _qapp()
    import ui.dialogs.setup_wizard as sw

    fake_hf = {
        "id": "test/stab5-hf-model",
        "display": "STAB5 HF Testmodell",
        "size_gb": 1.5,
        "description": "Nur fuer Test",
        "required": False,
        "default": True,
        "tags": ["hf"],
    }
    monkeypatch.setattr(sw, "_HF_MODELS", [fake_hf])
    monkeypatch.setattr(sw, "_hf_cache_has", lambda repo_id: False)

    page = sw._PageModels()
    page.show()
    app.processEvents()
    try:
        assert len(page.findChildren(QCheckBox)) == 3
        cb = page._checkboxes["test/stab5-hf-model"]
        assert cb.isVisibleTo(page) is True
        assert cb.isEnabled() is True
        assert cb.isChecked() is True
        assert page.selected_hf() == ["test/stab5-hf-model"]
        assert "4.8 GB" in page._size_lbl.text()

        _click_checkbox(cb)
        app.processEvents()

        assert cb.isChecked() is False
        assert page.selected_hf() == []
        assert "3.3 GB" in page._size_lbl.text()
    finally:
        page.deleteLater()
        app.processEvents()


def test_control_59_cancel_btn_cancels_worker_and_disables_itself() -> None:
    """#59: _cancel_btn -> Worker.cancel + disabled + Statustext."""
    app = _qapp()
    from ui.dialogs.setup_wizard import _PageDownload

    page = _PageDownload()
    page.show()
    app.processEvents()
    try:
        class _FakeWorker:
            cancelled = False

            def cancel(self):
                self.cancelled = True

        fake = _FakeWorker()
        page._worker = fake

        button = _single_button(page, "Abbrechen")
        assert button is page._cancel_btn

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert fake.cancelled is True
        assert button.isEnabled() is False
        assert page._status_lbl.text() == "Breche ab…"
    finally:
        page._worker = None
        page.deleteLater()
        app.processEvents()


def test_control_60_skip_btn_marks_complete_and_accepts(wizard_env) -> None:
    """#60: 'Überspringen' -> Setup-Flag + accept."""
    app = _qapp()
    sw = wizard_env
    wizard = _make_wizard(sw)
    try:
        assert sw.is_setup_complete() is False
        button = _single_button(wizard, "Überspringen")
        assert button is wizard._skip_btn

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert sw.is_setup_complete() is True
        assert wizard.result() == QDialog.DialogCode.Accepted
        assert wizard.isVisible() is False
    finally:
        wizard.deleteLater()
        app.processEvents()


def test_control_61_back_btn_returns_to_hardware_page(wizard_env) -> None:
    """#61: 'Zurück' -> Modelle -> Hardware."""
    app = _qapp()
    sw = wizard_env
    wizard = _make_wizard(sw)
    try:
        assert wizard._back_btn.isVisibleTo(wizard) is False

        QTest.mouseClick(_single_button(wizard, "Weiter →"), Qt.MouseButton.LeftButton)
        app.processEvents()
        assert wizard._stack.currentIndex() == sw.SetupWizard.PAGE_MODELS

        button = _single_button(wizard, "Zurück")
        assert button is wizard._back_btn
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert wizard._stack.currentIndex() == sw.SetupWizard.PAGE_HARDWARE
        assert wizard._back_btn.isVisibleTo(wizard) is False
        assert wizard.isVisible() is True
    finally:
        wizard.done(0)
        wizard.deleteLater()
        app.processEvents()


def test_control_62_next_btn_advances_to_models_page(wizard_env) -> None:
    """#62: 'Weiter →' -> Hardware -> Modelle, kein Download gestartet."""
    app = _qapp()
    sw = wizard_env
    wizard = _make_wizard(sw)
    try:
        button = _single_button(wizard, "Weiter →")
        assert button is wizard._next_btn

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert wizard._stack.currentIndex() == sw.SetupWizard.PAGE_MODELS
        assert wizard._back_btn.isVisibleTo(wizard) is True
        assert wizard._skip_btn.isVisibleTo(wizard) is True
        assert wizard._page_dl._thread is None
        assert wizard.isVisible() is True
    finally:
        wizard.done(0)
        wizard.deleteLater()
        app.processEvents()


def test_control_63_launch_btn_marks_complete_and_accepts(wizard_env) -> None:
    """#63: 'App starten  →' auf PAGE_FINISH -> Setup-Flag + accept."""
    app = _qapp()
    sw = wizard_env
    wizard = _make_wizard(sw)
    try:
        wizard._go_to(sw.SetupWizard.PAGE_FINISH)
        app.processEvents()

        assert wizard._next_btn.isVisibleTo(wizard) is False
        button = _single_button(wizard, "App starten  →")

        assert sw.is_setup_complete() is False
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert sw.is_setup_complete() is True
        assert wizard.result() == QDialog.DialogCode.Accepted
        assert wizard.isVisible() is False
    finally:
        wizard.deleteLater()
        app.processEvents()
