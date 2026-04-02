"""
PB Studio — Einstellungs-Dialog.

Aktuell: Ollama LLM-Backend-Konfiguration.
- Ollama-URL (Standard: http://localhost:11434)
- Modell-Auswahl (Dropdown + Refresh)
- Auto-Detection ("Test"-Button)
- Aktivieren/Deaktivieren

Einstellungen werden in QSettings (Registry/Ini) gespeichert
und sind sofort aktiv (kein Neustart nötig).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSettings, Signal, QObject, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QDialogButtonBox, QWidget, QFormLayout,
    QStatusBar,
)

from ui.theme import ACCENT, BG1, BG2, BG3, T1, T2, T3, OK, ERR, WARN

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SETTINGS_ORG = "PBStudio"
SETTINGS_APP = "PBStudio"


def _load_settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def get_ollama_settings() -> dict:
    """Gibt die gespeicherten Ollama-Einstellungen zurück."""
    s = _load_settings()
    return {
        "enabled": s.value("ollama/enabled", True, type=bool),
        "url": s.value("ollama/url", "http://localhost:11434", type=str),
        "model": s.value("ollama/model", "", type=str),
    }


def save_ollama_settings(enabled: bool, url: str, model: str) -> None:
    """Speichert Ollama-Einstellungen dauerhaft."""
    s = _load_settings()
    s.setValue("ollama/enabled", enabled)
    s.setValue("ollama/url", url)
    s.setValue("ollama/model", model)
    s.sync()


class _OllamaTestWorker(QObject):
    """Prüft Ollama-Verbindung und lädt Modell-Liste in einem Thread."""
    finished = Signal(bool, str, list)  # (ok, message, models)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            from services.ollama_client import OllamaClient
            client = OllamaClient(base_url=self.url, timeout=5)
            if not client.is_available():
                self.finished.emit(False, f"Ollama nicht erreichbar unter {self.url}", [])
                return
            version = client.get_version() or "?"
            models = client.list_models()
            self.finished.emit(
                True,
                f"Verbunden! Ollama v{version} — {len(models)} Modell(e) verfügbar.",
                models,
            )
        except Exception as e:
            self.finished.emit(False, f"Fehler: {e}", [])


_STATUS_STYLE = {
    "ok": f"color: {OK}; font-size: 12px;",
    "error": f"color: {ERR}; font-size: 12px;",
    "warn": f"color: {WARN}; font-size: 12px;",
    "info": f"color: {T2}; font-size: 12px;",
}

_DIALOG_STYLE = f"""
QDialog {{
    background-color: {BG1};
    color: {T1};
}}
QGroupBox {{
    background-color: {BG2};
    border: 1px solid {BG3};
    border-radius: 6px;
    margin-top: 8px;
    padding: 8px;
    font-weight: bold;
    color: {ACCENT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}
QLabel {{
    color: {T1};
}}
QLineEdit {{
    background-color: {BG3};
    border: 1px solid #374151;
    border-radius: 4px;
    color: {T1};
    padding: 4px 8px;
    min-height: 24px;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox {{
    background-color: {BG3};
    border: 1px solid #374151;
    border-radius: 4px;
    color: {T1};
    padding: 4px 8px;
    min-height: 24px;
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background-color: {BG3};
    color: {T1};
    selection-background-color: {ACCENT};
}}
QPushButton {{
    background-color: {BG3};
    color: {T1};
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 28px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {BG2};
}}
QCheckBox {{
    color: {T1};
    spacing: 6px;
}}
QDialogButtonBox QPushButton {{
    min-width: 90px;
}}
"""


class SettingsDialog(QDialog):
    """Einstellungs-Dialog für PB Studio.

    Enthält aktuell:
    - Ollama LLM-Backend-Konfiguration
    """

    ollama_settings_changed = Signal(bool, str, str)  # (enabled, url, model)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PB Studio — Einstellungen")
        self.setMinimumWidth(520)
        self.setStyleSheet(_DIALOG_STYLE)
        self._test_thread: QThread | None = None
        self._test_worker: _OllamaTestWorker | None = None

        self._build_ui()
        self._load_current_settings()

    def closeEvent(self, event) -> None:
        if self._test_thread is not None and self._test_thread.isRunning():
            self._test_thread.quit()
            self._test_thread.wait(2000)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 12)

        # --- Ollama-Gruppe ---
        ollama_group = QGroupBox("Lokales LLM-Backend (Ollama)")
        form_layout = QFormLayout(ollama_group)
        form_layout.setSpacing(8)

        # Aktivieren
        self._chk_enabled = QCheckBox("Ollama als LLM-Backend nutzen")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.toggled.connect(self._on_enabled_toggled)
        form_layout.addRow("", self._chk_enabled)

        # URL
        url_row = QWidget()
        url_layout = QHBoxLayout(url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)
        self._txt_url = QLineEdit("http://localhost:11434")
        self._txt_url.setPlaceholderText("http://localhost:11434")
        url_layout.addWidget(self._txt_url)
        self._btn_test = QPushButton("Verbindung testen")
        self._btn_test.setFixedWidth(150)
        self._btn_test.clicked.connect(self._on_test_clicked)
        url_layout.addWidget(self._btn_test)
        form_layout.addRow("Ollama-URL:", url_row)

        # Status-Label
        self._lbl_status = QLabel("—")
        self._lbl_status.setStyleSheet(_STATUS_STYLE["info"])
        self._lbl_status.setWordWrap(True)
        form_layout.addRow("Status:", self._lbl_status)

        # Modell-Auswahl
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(6)
        self._cmb_model = QComboBox()
        self._cmb_model.setEditable(True)
        self._cmb_model.setPlaceholderText("Modell wählen oder eingeben...")
        model_layout.addWidget(self._cmb_model, 1)
        self._btn_refresh = QPushButton("↻")
        self._btn_refresh.setFixedWidth(36)
        self._btn_refresh.setToolTip("Modell-Liste neu laden")
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        model_layout.addWidget(self._btn_refresh)
        form_layout.addRow("Modell:", model_row)

        # Empfehlungs-Hinweis
        from services.ollama_client import RECOMMENDED_MODELS
        hint_text = "Empfohlen für GTX 1060 (6 GB): " + ", ".join(RECOMMENDED_MODELS[:3])
        lbl_hint = QLabel(hint_text)
        lbl_hint.setStyleSheet(f"color: {T3}; font-size: 11px;")
        lbl_hint.setWordWrap(True)
        form_layout.addRow("", lbl_hint)

        layout.addWidget(ollama_group)

        # --- Modell-Manager ---
        mgr_group = QGroupBox("Modell-Verwaltung")
        mgr_layout = QHBoxLayout(mgr_group)
        lbl_mgr = QLabel("Modelle herunterladen, verwalten und ungenutzte aufräumen.")
        lbl_mgr.setStyleSheet(f"color: {T2}; font-size: 11px;")
        mgr_layout.addWidget(lbl_mgr, 1)
        self._btn_model_manager = QPushButton("⊞ Modell-Manager öffnen")
        self._btn_model_manager.setToolTip("Installierte Modelle anzeigen, neue herunterladen, aufräumen")
        self._btn_model_manager.clicked.connect(self._on_open_model_manager)
        mgr_layout.addWidget(self._btn_model_manager)
        layout.addWidget(mgr_group)

        # --- Info-Text ---
        lbl_info = QLabel(
            "Wenn Ollama nicht verfügbar ist, fällt PB Studio automatisch auf das lokale "
            "HuggingFace-Modell zurück (Qwen2.5-0.5B-Instruct)."
        )
        lbl_info.setStyleSheet(f"color: {T2}; font-size: 11px;")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        # --- Buttons ---
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Logik
    # ------------------------------------------------------------------

    def _load_current_settings(self) -> None:
        cfg = get_ollama_settings()
        self._chk_enabled.setChecked(cfg["enabled"])
        self._txt_url.setText(cfg["url"])
        if cfg["model"]:
            self._cmb_model.addItem(cfg["model"])
            self._cmb_model.setCurrentText(cfg["model"])
        self._on_enabled_toggled(cfg["enabled"])

    def _on_enabled_toggled(self, checked: bool) -> None:
        self._txt_url.setEnabled(checked)
        self._btn_test.setEnabled(checked)
        self._cmb_model.setEnabled(checked)
        self._btn_refresh.setEnabled(checked)

    def _set_status(self, text: str, kind: str = "info") -> None:
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(_STATUS_STYLE.get(kind, _STATUS_STYLE["info"]))

    def _on_test_clicked(self) -> None:
        url = self._txt_url.text().strip() or "http://localhost:11434"
        self._set_status("Teste Verbindung...", "info")
        self._btn_test.setEnabled(False)

        self._test_thread = QThread(self)
        self._test_worker = _OllamaTestWorker(url=url)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.finished.connect(self._test_thread.quit)
        self._test_thread.start()

    def _on_test_finished(self, ok: bool, message: str, models: list) -> None:
        if not self.isVisible():
            return
        self._btn_test.setEnabled(self._chk_enabled.isChecked())
        if ok:
            self._set_status(message, "ok")
            self._populate_models(models)
        else:
            self._set_status(message, "error")

    def _on_refresh_clicked(self) -> None:
        self._on_test_clicked()

    def _populate_models(self, models: list[str]) -> None:
        """Befüllt die Modell-ComboBox mit verfügbaren Ollama-Modellen."""
        current = self._cmb_model.currentText()
        self._cmb_model.clear()
        self._cmb_model.addItems(models)
        if current in models:
            self._cmb_model.setCurrentText(current)
        elif models:
            self._cmb_model.setCurrentIndex(0)

    def _on_open_model_manager(self) -> None:
        """Öffnet den Modell-Manager Dialog."""
        from ui.dialogs.model_manager_dialog import ModelManagerDialog
        url = self._txt_url.text().strip() or "http://localhost:11434"
        dlg = ModelManagerDialog(parent=self, ollama_url=url)
        dlg.exec()

    def _on_accept(self) -> None:
        enabled = self._chk_enabled.isChecked()
        url = self._txt_url.text().strip() or "http://localhost:11434"
        model = self._cmb_model.currentText().strip()

        save_ollama_settings(enabled=enabled, url=url, model=model)
        self.ollama_settings_changed.emit(enabled, url, model)
        logger.info(
            "SettingsDialog: Ollama-Einstellungen gespeichert — enabled=%s, url=%s, model=%s",
            enabled, url, model,
        )
        self.accept()
