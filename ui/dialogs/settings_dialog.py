"""
PB Studio — Einstellungs-Dialog.

Tabs:
- LLM Backend: Ollama-Konfiguration
- Shortcuts:   Konfigurierbares Tastaturkürzel-Mapping (AUD-71)

Einstellungen werden in JSON-Format gespeichert
und sind sofort aktiv (kein Neustart nötig).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QDialogButtonBox, QWidget, QFormLayout,
    QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)

from ui.theme import ACCENT, BG1, BG2, BG3, T1, T2, T3, OK, ERR, WARN

if TYPE_CHECKING:
    pass

from services.timeout_constants import HTTP_API_TIMEOUT_SEC
from services.settings_store import get_settings_store, get_ollama_settings

logger = logging.getLogger(__name__)


def save_ollama_settings(enabled: bool, url: str, model: str) -> None:
    """Speichert Ollama-Einstellungen dauerhaft."""
    get_settings_store().save_ollama_settings(enabled, url, model)


class _OllamaTestWorker(QObject):
    """Prüft Ollama-Verbindung und lädt Modell-Liste in einem Thread."""
    finished = Signal(bool, str, list)  # (ok, message, models)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            from services.ollama_client import OllamaClient
            client = OllamaClient(base_url=self.url, timeout=HTTP_API_TIMEOUT_SEC)
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
        except (ImportError, OSError, RuntimeError) as e:
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


# ---------------------------------------------------------------------------
# Key-capture dialog
# ---------------------------------------------------------------------------

class _KeyCaptureDialog(QDialog):
    """Modal dialog that captures a single key-press as a QKeySequence."""

    def __init__(self, action_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shortcut aufzeichnen")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setFixedSize(360, 140)
        self.setStyleSheet(_DIALOG_STYLE)
        self._captured: QKeySequence | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        lbl = QLabel(f'Neue Tastenkombination für <b>{action_name}</b>:')
        lbl.setStyleSheet(f"color: {T1};")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self._lbl_key = QLabel("— drücke eine Taste —")
        self._lbl_key.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_key.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight: bold;"
            f" background: {BG3}; border-radius: 6px; padding: 6px;"
        )
        layout.addWidget(self._lbl_key)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return  # ignore bare modifier presses
        seq = QKeySequence(key | int(event.modifiers()))
        self._captured = seq
        self._lbl_key.setText(seq.toString())

    def captured_sequence(self) -> QKeySequence | None:
        return self._captured


# ---------------------------------------------------------------------------
# Shortcut Editor Tab
# ---------------------------------------------------------------------------

class ShortcutEditorTab(QWidget):
    """Tab widget showing all configurable shortcuts in a table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.shortcut_manager import get_shortcut_manager, ACTIONS
        self._sm = get_shortcut_manager()
        self._actions = ACTIONS
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 8)

        lbl = QLabel("Doppelklick auf eine Zeile oder 'Bearbeiten' um den Shortcut zu ändern.")
        lbl.setStyleSheet(f"color: {T2}; font-size: 11px;")
        lbl.setToolTip(
            "Shortcut-Tabelle: Aktion auswaehlen und per Doppelklick oder Bearbeiten neu belegen."
        )
        layout.addWidget(lbl)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Aktion", "Beschreibung", "Shortcut"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setToolTip(
            "Konfigurierbare Tastaturkuerzel. Doppelklick auf eine Zeile startet die Aufnahme."
        )
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {BG2}; color: {T1}; gridline-color: {BG3};"
            f" alternate-background-color: {BG1}; border: 1px solid {BG3}; }}"
            f"QHeaderView::section {{ background: {BG3}; color: {T1}; border: none;"
            f" padding: 4px 8px; font-weight: bold; }}"
            f"QTableWidget::item:selected {{ background: {ACCENT}; color: #000; }}"
        )
        self._table.itemDoubleClicked.connect(self._edit_selected)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._btn_edit = QPushButton("Bearbeiten")
        self._btn_edit.setToolTip(
            "Ausgewaehltes Tastaturkuerzel neu aufnehmen."
        )
        self._btn_edit.clicked.connect(self._edit_selected)
        self._btn_reset = QPushButton("Alle zurücksetzen")
        self._btn_reset.setToolTip(
            "Alle Tastaturkuerzel auf PB-Studio-Standardwerte zuruecksetzen."
        )
        self._btn_reset.clicked.connect(self._reset_all)
        btn_row.addWidget(self._btn_edit)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_reset)
        layout.addLayout(btn_row)

    def _populate(self) -> None:
        self._table.setRowCount(0)
        for action_id, (name, desc, _default) in self._actions.items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.ItemDataRole.UserRole, action_id)
            self._table.setItem(row, 0, item_name)
            self._table.setItem(row, 1, QTableWidgetItem(desc))
            self._table.setItem(row, 2, QTableWidgetItem(
                self._sm.display_text(action_id)
            ))

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name_item = self._table.item(row, 0)
        action_id = name_item.data(Qt.ItemDataRole.UserRole)
        action_name = name_item.text()

        dlg = _KeyCaptureDialog(action_name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_sequence():
            seq = dlg.captured_sequence()
            self._sm.set_sequence(action_id, seq)
            self._table.item(row, 2).setText(seq.toString())

    def _reset_all(self) -> None:
        self._sm.reset_to_defaults()
        self._populate()

    def apply(self) -> None:
        """Persist changes — called by SettingsDialog on OK."""
        self._sm.save()


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """Einstellungs-Dialog für PB Studio.

    Tabs:
    - LLM Backend (Ollama)
    - Shortcuts (AUD-71)
    """

    ollama_settings_changed = Signal(bool, str, str)  # (enabled, url, model)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PB Studio — Einstellungen")
        self.setMinimumWidth(560)
        self.setMinimumHeight(440)
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
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 10)

        # --- Tab-Widget ---
        self._tabs = QTabWidget()
        self._tabs.setToolTip(
            "Einstellungsbereiche fuer lokales LLM-Backend und Tastaturkuerzel."
        )
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {BG3}; background: {BG1}; }}"
            f"QTabBar::tab {{ background: {BG2}; color: {T2}; padding: 6px 16px;"
            f" border: 1px solid {BG3}; border-bottom: none; border-radius: 4px 4px 0 0; }}"
            f"QTabBar::tab:selected {{ background: {BG1}; color: {ACCENT}; }}"
        )
        layout.addWidget(self._tabs, 1)

        # ---- Tab 1: LLM Backend ----
        llm_tab = QWidget()
        llm_layout = QVBoxLayout(llm_tab)
        llm_layout.setSpacing(12)
        llm_layout.setContentsMargins(12, 12, 12, 8)

        # Ollama-Gruppe
        ollama_group = QGroupBox("Lokales LLM-Backend (Ollama)")
        form_layout = QFormLayout(ollama_group)
        form_layout.setSpacing(8)

        self._chk_enabled = QCheckBox("Ollama als LLM-Backend nutzen")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.setToolTip(
            "Aktiviert Ollama als lokales LLM-Backend fuer Agenten- und Caption-Aufgaben."
        )
        self._chk_enabled.toggled.connect(self._on_enabled_toggled)
        form_layout.addRow("", self._chk_enabled)

        url_row = QWidget()
        url_layout = QHBoxLayout(url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)
        self._txt_url = QLineEdit("http://localhost:11434")
        self._txt_url.setPlaceholderText("http://localhost:11434")
        self._txt_url.setToolTip(
            "Basis-URL des lokalen Ollama-Servers. Standard ist http://localhost:11434."
        )
        url_layout.addWidget(self._txt_url)
        self._btn_test = QPushButton("Verbindung testen")
        self._btn_test.setFixedWidth(150)
        self._btn_test.setToolTip(
            "Ollama-Verbindung pruefen und installierte Modelle laden."
        )
        self._btn_test.clicked.connect(self._on_test_clicked)
        url_layout.addWidget(self._btn_test)
        form_layout.addRow("Ollama-URL:", url_row)

        self._lbl_status = QLabel("—")
        self._lbl_status.setStyleSheet(_STATUS_STYLE["info"])
        self._lbl_status.setWordWrap(True)
        form_layout.addRow("Status:", self._lbl_status)

        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(6)
        self._cmb_model = QComboBox()
        self._cmb_model.setEditable(True)
        self._cmb_model.setPlaceholderText("Modell wählen oder eingeben...")
        self._cmb_model.setToolTip(
            "Ollama-Modell fuer lokale LLM-Aufgaben waehlen oder Modellnamen manuell eingeben."
        )
        model_layout.addWidget(self._cmb_model, 1)
        self._btn_refresh = QPushButton("↻")
        self._btn_refresh.setFixedWidth(36)
        self._btn_refresh.setToolTip(
            "Modell-Liste vom Ollama-Server neu laden."
        )
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        model_layout.addWidget(self._btn_refresh)
        form_layout.addRow("Modell:", model_row)

        from services.ollama_client import RECOMMENDED_MODELS
        hint_text = "Empfohlen für GTX 1060 (6 GB): " + ", ".join(RECOMMENDED_MODELS[:3])
        lbl_hint = QLabel(hint_text)
        lbl_hint.setStyleSheet(f"color: {T3}; font-size: 11px;")
        lbl_hint.setWordWrap(True)
        form_layout.addRow("", lbl_hint)

        llm_layout.addWidget(ollama_group)

        mgr_group = QGroupBox("Modell-Verwaltung")
        mgr_layout = QHBoxLayout(mgr_group)
        lbl_mgr = QLabel("Modelle herunterladen, verwalten und ungenutzte aufräumen.")
        lbl_mgr.setStyleSheet(f"color: {T2}; font-size: 11px;")
        mgr_layout.addWidget(lbl_mgr, 1)
        self._btn_model_manager = QPushButton("⊞ Modell-Manager öffnen")
        self._btn_model_manager.setToolTip(
            "Modell-Manager oeffnen: installierte Modelle anzeigen, neue Modelle herunterladen und ungenutzte aufraeumen."
        )
        self._btn_model_manager.clicked.connect(self._on_open_model_manager)
        mgr_layout.addWidget(self._btn_model_manager)
        llm_layout.addWidget(mgr_group)

        storage_group = QGroupBox("Storage")
        storage_layout = QHBoxLayout(storage_group)
        lbl_storage = QLabel("Globale Analyse-Artefakte projektuebergreifend ansehen und bereinigen.")
        lbl_storage.setStyleSheet(f"color: {T2}; font-size: 11px;")
        lbl_storage.setWordWrap(True)
        storage_layout.addWidget(lbl_storage, 1)
        self._btn_storage_browser = QPushButton("Storage-Browser")
        self._btn_storage_browser.setToolTip(
            "Storage-Browser oeffnen: analysierte Dateien projektuebergreifend listen und Analysen nach Bestaetigung loeschen."
        )
        self._btn_storage_browser.clicked.connect(self._on_open_storage_browser)
        storage_layout.addWidget(self._btn_storage_browser)
        llm_layout.addWidget(storage_group)

        lbl_info = QLabel(
            "Wenn Ollama nicht verfügbar ist, fällt PB Studio automatisch auf das lokale "
            "HuggingFace-Modell zurück (Gemma 4 E4B)."
        )
        lbl_info.setStyleSheet(f"color: {T2}; font-size: 11px;")
        lbl_info.setWordWrap(True)
        llm_layout.addWidget(lbl_info)
        llm_layout.addStretch()

        self._tabs.addTab(llm_tab, "LLM Backend")
        self._tabs.setTabToolTip(0, "Ollama-Backend, Server-URL und Modell fuer KI-Funktionen konfigurieren.")

        # ---- Tab 2: Analyse (NEUBAU-VOLLINTEGRATION T2.2 / USE-012) ----
        analyse_tab = QWidget()
        analyse_layout = QVBoxLayout(analyse_tab)
        audio_group = QGroupBox("Audio-Analyse")
        audio_form = QVBoxLayout(audio_group)
        self._chk_audio_v2_default = QCheckBox("Audio-Analyse V2 als Standard")
        self._chk_audio_v2_default.setToolTip(
            "AN: Komplett-Analyse nutzt die V2-Pipeline (parallelisiert, "
            "Status-Panel).\nAUS: klassischer sequenzieller Pfad "
            "(_analyze_all_sequential) als Standard."
        )
        audio_form.addWidget(self._chk_audio_v2_default)
        lbl_v2 = QLabel(
            "Gilt fuer 'Audio komplett analysieren' und die Komplett-Analyse. "
            "Wirkt sofort, kein Neustart noetig."
        )
        lbl_v2.setStyleSheet(f"color: {T2}; font-size: 11px;")
        lbl_v2.setWordWrap(True)
        audio_form.addWidget(lbl_v2)
        analyse_layout.addWidget(audio_group)
        analyse_layout.addStretch()
        self._tabs.addTab(analyse_tab, "Analyse")
        self._tabs.setTabToolTip(1, "Analyse-Pipelines konfigurieren (Audio V2 als Standard).")

        # ---- Tab 3: Shortcuts (AUD-71) ----
        self._shortcut_tab = ShortcutEditorTab()
        self._tabs.addTab(self._shortcut_tab, "Tastaturkürzel")
        self._tabs.setTabToolTip(2, "Tastaturkuerzel ansehen, bearbeiten oder auf Standard zuruecksetzen.")

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
        # T2.2 (USE-012): audio.v2_default — Default True wie der Leser
        # in ui/controllers/audio_analysis.py
        self._chk_audio_v2_default.setChecked(bool(
            get_settings_store().get_nested("audio", "v2_default", default=True)
        ))

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

    def _on_open_storage_browser(self) -> None:
        from ui.dialogs.storage_browser_dialog import StorageBrowserDialog

        dlg = StorageBrowserDialog(parent=self)
        dlg.exec()

    def _validate_ollama_model(self, url: str, model: str) -> bool:
        """B-195: Prueft ob ``model`` auf ``url`` installiert ist.

        Returns:
            True   = Modell installiert ODER Ollama unerreichbar (lassen
                     wir durch, damit Offline-Setups arbeitsfaehig bleiben)
                     ODER User wollte explizit trotzdem speichern.
            False  = Modell fehlt UND User hat den Save-Versuch abgebrochen.
        """
        try:
            from services.ollama_client import OllamaClient

            client = OllamaClient(base_url=url)
            installed = client.list_models()
        except Exception as exc:  # broad: jede Verbindungs-/Import-Pleite
            logger.warning(
                "B-195: Modell-Validierung fehlgeschlagen (%s) — "
                "lasse Speichern zu (Offline-Modus).", exc,
            )
            return True

        if not installed:
            # ollama lieferte leere Liste → wahrscheinlich nicht erreichbar
            # oder gerade frisch ohne Modelle. Nicht hart blockieren.
            logger.info(
                "B-195: Ollama-Modellliste leer fuer %s — Speichern zugelassen.",
                url,
            )
            return True

        if model in installed:
            return True

        # Modell fehlt — User-Bestaetigung einholen
        from PySide6.QtWidgets import QMessageBox

        preview = ", ".join(installed[:5])
        if len(installed) > 5:
            preview += f", … (+{len(installed) - 5})"

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Ollama-Modell nicht installiert")
        msg.setText(
            f"Das Modell '{model}' ist auf {url} NICHT installiert."
        )
        msg.setInformativeText(
            "Pipeline-Aufrufe wuerden mit HTTP 404 scheitern und "
            "Hintergrund-Worker koennen mehrere Minuten in Timeouts "
            "haengen.\n\n"
            f"Installierte Modelle: {preview}\n\n"
            "Trotzdem speichern oder abbrechen?"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Save
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        choice = msg.exec()
        return choice == QMessageBox.StandardButton.Save

    def _on_accept(self) -> None:
        enabled = self._chk_enabled.isChecked()
        url = self._txt_url.text().strip() or "http://localhost:11434"
        model = self._cmb_model.currentText().strip()

        # B-195: Pre-Check vor Save — ist das Modell auf diesem Ollama-Server
        # installiert? Verhindert dass die nachfolgende Pipeline auf jeden
        # Caption-Call ein 404 bekommt, in 15s-Timeouts haengt und im
        # schlimmsten Fall einen nativen Crash triggert (gemeldet 2026-04-27
        # nach Conda-Migration: 12420ms MouseRelease + SIGSEGV).
        if enabled and model and not self._validate_ollama_model(url, model):
            return  # User hat im Validierungs-Dialog abgebrochen

        save_ollama_settings(enabled=enabled, url=url, model=model)
        self.ollama_settings_changed.emit(enabled, url, model)
        logger.info(
            "SettingsDialog: Ollama-Einstellungen gespeichert — enabled=%s, url=%s, model=%s",
            enabled, url, model,
        )

        # T2.2 (USE-012): audio.v2_default persistieren — erster echter
        # set_nested-Schreiber fuer dieses Setting.
        v2_default = self._chk_audio_v2_default.isChecked()
        get_settings_store().set_nested("audio", "v2_default", value=v2_default)
        logger.info("SettingsDialog: audio.v2_default gespeichert = %s", v2_default)

        # Save shortcut changes (AUD-71)
        self._shortcut_tab.apply()

        self.accept()
