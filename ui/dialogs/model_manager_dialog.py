"""
Modell-Manager Dialog — AP-4 (AUD-11).

UI für Modell-Lifecycle-Management:
- Tab 1 "Installiert": Übersicht aller installierten Modelle (Ollama + HF)
- Tab 2 "Download": Empfohlene Modelle herunterladen mit Progress-Bar
- Tab 3 "Cleanup": Ungenutzte Modelle identifizieren und löschen

Öffnbar via: Einstellungen → "Modell-Manager öffnen"
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QProgressBar, QLineEdit, QGroupBox, QFrame,
    QMessageBox, QSpinBox, QHeaderView,
    QAbstractItemView,
)

from ui.theme import ACCENT, BG1, BG2, BG3, T1, T2, T3, OK, ERR, WARN

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Hintergrund-Worker
# ──────────────────────────────────────────────────────────────────────────────

class _ScanWorker(QObject):
    """Scannt Ollama + HF Cache im Hintergrund."""
    finished = Signal(list)     # list[ModelEntry]
    error = Signal(str)

    def __init__(self, ollama_url: str):
        super().__init__()
        self.ollama_url = ollama_url

    def run(self) -> None:
        try:
            from services.model_lifecycle_service import get_model_lifecycle_service
            svc = get_model_lifecycle_service(self.ollama_url)
            entries = svc.scan_all()
            self.finished.emit(entries)
        except (ImportError, OSError, RuntimeError) as e:
            self.error.emit(str(e))


class _ProgressRelay(QObject):
    """Leitet Thread-sichere Progress-Updates an den GUI-Thread weiter."""
    update = Signal(object)     # DownloadProgress


# ──────────────────────────────────────────────────────────────────────────────
# Haupt-Dialog
# ──────────────────────────────────────────────────────────────────────────────

class ModelManagerDialog(QDialog):
    """Vollständiger Modell-Manager Dialog."""

    def __init__(self, parent=None, ollama_url: str = "http://localhost:11434"):
        super().__init__(parent)
        self.ollama_url = ollama_url
        self._scan_thread: QThread | None = None
        self._scan_worker: _ScanWorker | None = None
        self._progress_relays: dict[str, _ProgressRelay] = {}
        self._download_rows: dict[str, int] = {}  # model_id → Tabellenzeile
        self._entries: list = []

        self.setWindowTitle("Modell-Manager — PB Studio")
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)
        self._apply_styles()
        self._build_ui()

        # Initialen Scan starten
        QTimer.singleShot(100, self._start_scan)

    def closeEvent(self, event) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
        super().closeEvent(event)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {BG1}; color: {T1}; }}
            QTabWidget::pane {{ border: 1px solid {BG3}; background: {BG1}; }}
            QTabBar::tab {{
                background: {BG2}; color: {T2}; padding: 8px 16px;
                border: 1px solid {BG3}; border-bottom: none;
            }}
            QTabBar::tab:selected {{ background: {BG1}; color: {T1}; }}
            QTableWidget {{
                background: {BG2}; color: {T1};
                border: 1px solid {BG3}; gridline-color: {BG3};
                selection-background-color: {ACCENT};
            }}
            QTableWidget QHeaderView::section {{
                background: {BG3}; color: {T1}; padding: 6px;
                border: 1px solid {BG2};
            }}
            QPushButton {{
                background: {BG3}; color: {T1}; border: 1px solid {BG3};
                padding: 6px 14px; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
            QPushButton:disabled {{ color: {T3}; }}
            QLineEdit {{
                background: {BG2}; color: {T1};
                border: 1px solid {BG3}; padding: 4px 8px; border-radius: 3px;
            }}
            QProgressBar {{
                background: {BG3}; border: 1px solid {BG2}; border-radius: 3px;
                text-align: center; color: {T1};
            }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
            QGroupBox {{
                border: 1px solid {BG3}; border-radius: 4px;
                margin-top: 8px; padding-top: 8px; color: {T2};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {T1}; }}
            QLabel {{ color: {T1}; }}
            QScrollArea {{ border: none; background: transparent; }}
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("KI-Modell-Manager")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {T1};")
        header.addWidget(title)
        header.addStretch()

        self._ollama_status_lbl = QLabel("Ollama: prüfe...")
        self._ollama_status_lbl.setStyleSheet(f"color: {WARN}; font-size: 11px;")
        header.addWidget(self._ollama_status_lbl)

        self._refresh_btn = QPushButton("⟳ Aktualisieren")
        self._refresh_btn.clicked.connect(self._start_scan)
        header.addWidget(self._refresh_btn)

        layout.addLayout(header)

        # Tabs
        self._tabs = QTabWidget()
        self._installed_tab = self._build_installed_tab()
        self._download_tab = self._build_download_tab()
        self._cleanup_tab = self._build_cleanup_tab()

        self._tabs.addTab(self._installed_tab, "Installiert")
        self._tabs.addTab(self._download_tab, "Download")
        self._tabs.addTab(self._cleanup_tab, "Cleanup")
        layout.addWidget(self._tabs)

        # Status-Zeile
        self._status_lbl = QLabel("Bereit.")
        self._status_lbl.setStyleSheet(f"color: {T3}; font-size: 10px;")
        layout.addWidget(self._status_lbl)

    # ──────────────────────────────────────────────────────────────────────
    # Tab 1: Installierte Modelle
    # ──────────────────────────────────────────────────────────────────────

    def _build_installed_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # Tabelle
        self._installed_table = QTableWidget(0, 6)
        self._installed_table.setHorizontalHeaderLabels([
            "Modell", "Quelle", "Größe", "Status", "Letzte Nutzung", "Aktionen"
        ])
        self._installed_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._installed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._installed_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._installed_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._installed_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._installed_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._installed_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._installed_table.setAlternatingRowColors(True)
        self._installed_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._installed_table.verticalHeader().setVisible(False)

        layout.addWidget(self._installed_table)

        # Info-Label
        self._installed_info = QLabel("Lade Modell-Liste...")
        self._installed_info.setStyleSheet(f"color: {T3}; font-size: 10px;")
        layout.addWidget(self._installed_info)

        return widget

    def _populate_installed_table(self, entries: list):
        """Füllt die installierte-Modelle-Tabelle."""
        self._installed_table.setRowCount(0)
        total_size_mb = 0.0

        for entry in entries:
            row = self._installed_table.rowCount()
            self._installed_table.insertRow(row)

            # Modell-Name
            name_item = QTableWidgetItem(entry.display_name)
            name_item.setData(Qt.UserRole, entry.model_id)
            self._installed_table.setItem(row, 0, name_item)

            # Quelle
            source_item = QTableWidgetItem(entry.source.upper())
            source_item.setTextAlignment(Qt.AlignCenter)
            if entry.source == "ollama":
                source_item.setForeground(
                    __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(ACCENT)
                )
            self._installed_table.setItem(row, 1, source_item)

            # Größe
            size_item = QTableWidgetItem(entry.size_display)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._installed_table.setItem(row, 2, size_item)
            total_size_mb += entry.size_mb

            # Status
            status_item = QTableWidgetItem(entry.status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if entry.status == "installed":
                status_item.setForeground(
                    __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(OK)
                )
            elif entry.status == "error":
                status_item.setForeground(
                    __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(ERR)
                )
            elif entry.status == "offline":
                status_item.setForeground(
                    __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(WARN)
                )
            self._installed_table.setItem(row, 3, status_item)

            # Letzte Nutzung
            used_item = QTableWidgetItem(entry.last_used_display)
            used_item.setTextAlignment(Qt.AlignCenter)
            self._installed_table.setItem(row, 4, used_item)

            # Aktionen (Löschen-Button)
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(4)

            del_btn = QPushButton("Löschen")
            del_btn.setStyleSheet(f"background: #5a2020; color: {T1}; padding: 3px 8px;")
            del_btn.setProperty("model_id", entry.model_id)
            del_btn.setProperty("source", entry.source)
            del_btn.clicked.connect(lambda checked, m=entry.model_id, s=entry.source:
                                    self._on_delete_model(m, s))
            action_layout.addWidget(del_btn)
            action_layout.addStretch()

            self._installed_table.setCellWidget(row, 5, action_widget)

        # Info-Label aktualisieren
        count = len(entries)
        if total_size_mb >= 1024:
            size_str = f"{total_size_mb / 1024:.1f} GB"
        else:
            size_str = f"{total_size_mb:.0f} MB"
        self._installed_info.setText(f"{count} Modelle installiert — Gesamt: {size_str}")

    # ──────────────────────────────────────────────────────────────────────
    # Tab 2: Download
    # ──────────────────────────────────────────────────────────────────────

    def _build_download_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # Ollama Section
        ollama_group = QGroupBox("Ollama-Modelle")
        ollama_layout = QVBoxLayout(ollama_group)

        ollama_hint = QLabel(
            "Empfohlene Modelle für Ihren PC (optimiert für GTX 1060 6GB). "
            "Ollama muss laufen ('ollama serve')."
        )
        ollama_hint.setWordWrap(True)
        ollama_hint.setStyleSheet(f"color: {T2}; font-size: 10px;")
        ollama_layout.addWidget(ollama_hint)

        # Download-Tabelle für Ollama
        self._ollama_dl_table = QTableWidget(0, 4)
        self._ollama_dl_table.setHorizontalHeaderLabels(["Modell", "Größe", "Beschreibung", "Aktion"])
        self._ollama_dl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._ollama_dl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._ollama_dl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._ollama_dl_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._ollama_dl_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._ollama_dl_table.verticalHeader().setVisible(False)
        self._ollama_dl_table.setAlternatingRowColors(True)
        self._ollama_dl_table.setMaximumHeight(250)
        ollama_layout.addWidget(self._ollama_dl_table)

        # Custom Ollama model
        custom_ollama_layout = QHBoxLayout()
        custom_ollama_layout.addWidget(QLabel("Eigenes Modell:"))
        self._custom_ollama_input = QLineEdit()
        self._custom_ollama_input.setPlaceholderText("z.B. llama3:latest")
        custom_ollama_layout.addWidget(self._custom_ollama_input)
        custom_pull_btn = QPushButton("Herunterladen")
        custom_pull_btn.clicked.connect(self._on_custom_ollama_pull)
        custom_ollama_layout.addWidget(custom_pull_btn)
        ollama_layout.addLayout(custom_ollama_layout)

        layout.addWidget(ollama_group)

        # HuggingFace Section
        hf_group = QGroupBox("HuggingFace-Modelle")
        hf_layout = QVBoxLayout(hf_group)

        hf_hint = QLabel(
            "Lokale Modelle aus dem HuggingFace-Hub. "
            "Whisper (Transkription), SigLIP (Video-Analyse), Moondream (Vision)."
        )
        hf_hint.setWordWrap(True)
        hf_hint.setStyleSheet(f"color: {T2}; font-size: 10px;")
        hf_layout.addWidget(hf_hint)

        # Download-Tabelle für HF
        self._hf_dl_table = QTableWidget(0, 4)
        self._hf_dl_table.setHorizontalHeaderLabels(["Modell", "Größe", "Beschreibung", "Aktion"])
        self._hf_dl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._hf_dl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._hf_dl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._hf_dl_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._hf_dl_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._hf_dl_table.verticalHeader().setVisible(False)
        self._hf_dl_table.setAlternatingRowColors(True)
        self._hf_dl_table.setMaximumHeight(200)
        hf_layout.addWidget(self._hf_dl_table)

        # Custom HF model
        custom_hf_layout = QHBoxLayout()
        custom_hf_layout.addWidget(QLabel("Repo-ID:"))
        self._custom_hf_input = QLineEdit()
        self._custom_hf_input.setPlaceholderText("z.B. microsoft/phi-2")
        custom_hf_layout.addWidget(self._custom_hf_input)
        custom_hf_btn = QPushButton("Herunterladen")
        custom_hf_btn.clicked.connect(self._on_custom_hf_download)
        custom_hf_layout.addWidget(custom_hf_btn)
        hf_layout.addLayout(custom_hf_layout)

        layout.addWidget(hf_group)

        # Progress-Bereich
        progress_group = QGroupBox("Laufende Downloads")
        self._progress_layout = QVBoxLayout(progress_group)
        self._no_downloads_lbl = QLabel("Keine aktiven Downloads.")
        self._no_downloads_lbl.setStyleSheet(f"color: {T3};")
        self._progress_layout.addWidget(self._no_downloads_lbl)
        layout.addWidget(progress_group)

        layout.addStretch()

        # Tabellen befüllen
        self._populate_dl_tables()

        return widget

    def _populate_dl_tables(self):
        """Befüllt die Download-Tabellen mit empfohlenen Modellen."""
        from services.model_lifecycle_service import RECOMMENDED_OLLAMA_MODELS, RECOMMENDED_HF_MODELS

        def _fill_table(table: QTableWidget, models: list, source: str):
            table.setRowCount(0)
            installed_ids = {e.model_id for e in self._entries}

            for m in models:
                row = table.rowCount()
                table.insertRow(row)

                table.setItem(row, 0, QTableWidgetItem(m["display"]))

                size_str = f"{m['size_gb']:.1f} GB"
                size_item = QTableWidgetItem(size_str)
                size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, 1, size_item)

                table.setItem(row, 2, QTableWidgetItem(m["description"]))

                # Action-Widget
                action_w = QWidget()
                action_l = QHBoxLayout(action_w)
                action_l.setContentsMargins(4, 2, 4, 2)

                if m["id"] in installed_ids:
                    lbl = QLabel("✓ Installiert")
                    lbl.setStyleSheet(f"color: {OK}; font-size: 10px;")
                    action_l.addWidget(lbl)
                else:
                    dl_btn = QPushButton("⬇ Herunterladen")
                    dl_btn.setStyleSheet(f"background: #1a3a5a; color: {T1}; padding: 3px 8px;")
                    if source == "ollama":
                        dl_btn.clicked.connect(
                            lambda checked, mid=m["id"]: self._on_pull_ollama(mid)
                        )
                    else:
                        dl_btn.clicked.connect(
                            lambda checked, mid=m["id"]: self._on_download_hf(mid)
                        )
                    action_l.addWidget(dl_btn)

                table.setCellWidget(row, 3, action_w)

        _fill_table(self._ollama_dl_table, RECOMMENDED_OLLAMA_MODELS, "ollama")
        _fill_table(self._hf_dl_table, RECOMMENDED_HF_MODELS, "huggingface")

    # ──────────────────────────────────────────────────────────────────────
    # Tab 3: Cleanup
    # ──────────────────────────────────────────────────────────────────────

    def _build_cleanup_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # Einstellungen
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Ungenutzt seit mehr als:"))
        self._days_spin = QSpinBox()
        self._days_spin.setRange(1, 365)
        self._days_spin.setValue(30)
        self._days_spin.setSuffix(" Tagen")
        self._days_spin.setStyleSheet(f"background: {BG2}; color: {T1}; border: 1px solid {BG3}; padding: 3px;")
        settings_layout.addWidget(self._days_spin)

        scan_btn = QPushButton("Analyse starten")
        scan_btn.clicked.connect(self._on_cleanup_scan)
        settings_layout.addWidget(scan_btn)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        # Kandidaten-Tabelle
        self._cleanup_table = QTableWidget(0, 5)
        self._cleanup_table.setHorizontalHeaderLabels([
            "Modell", "Quelle", "Größe", "Letzte Nutzung", "Aktion"
        ])
        self._cleanup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._cleanup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._cleanup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._cleanup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._cleanup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._cleanup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cleanup_table.verticalHeader().setVisible(False)
        self._cleanup_table.setAlternatingRowColors(True)
        self._cleanup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self._cleanup_table)

        # Info + Bulk-Aktion
        bottom_layout = QHBoxLayout()
        self._cleanup_info = QLabel("Klicken Sie 'Analyse starten' für Vorschläge.")
        self._cleanup_info.setStyleSheet(f"color: {T3}; font-size: 10px;")
        bottom_layout.addWidget(self._cleanup_info)
        bottom_layout.addStretch()

        self._delete_all_btn = QPushButton("Alle ausgewählten löschen")
        self._delete_all_btn.setStyleSheet(f"background: #5a2020; color: {T1};")
        self._delete_all_btn.setEnabled(False)
        self._delete_all_btn.clicked.connect(self._on_delete_all_selected)
        bottom_layout.addWidget(self._delete_all_btn)
        layout.addLayout(bottom_layout)

        return widget

    def _populate_cleanup_table(self, candidates: list):
        """Füllt die Cleanup-Kandidaten-Tabelle."""
        self._cleanup_table.setRowCount(0)
        total_size = 0.0

        for entry in candidates:
            row = self._cleanup_table.rowCount()
            self._cleanup_table.insertRow(row)

            self._cleanup_table.setItem(row, 0, QTableWidgetItem(entry.display_name))

            source_item = QTableWidgetItem(entry.source.upper())
            source_item.setTextAlignment(Qt.AlignCenter)
            self._cleanup_table.setItem(row, 1, source_item)

            size_item = QTableWidgetItem(entry.size_display)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._cleanup_table.setItem(row, 2, size_item)
            total_size += entry.size_mb

            used_text = entry.last_used_display
            if entry.days_since_used == -1:
                used_text = "Nie genutzt"
            used_item = QTableWidgetItem(used_text)
            used_item.setTextAlignment(Qt.AlignCenter)
            from PySide6.QtGui import QColor
            used_item.setForeground(QColor(WARN) if entry.days_since_used == -1 else QColor(T2))
            self._cleanup_table.setItem(row, 3, used_item)

            del_btn = QPushButton("Löschen")
            del_btn.setStyleSheet(f"background: #5a2020; color: {T1}; padding: 3px 8px;")
            del_btn.clicked.connect(lambda checked, m=entry.model_id, s=entry.source:
                                    self._on_delete_model(m, s))
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(4, 2, 4, 2)
            wl.addWidget(del_btn)
            self._cleanup_table.setCellWidget(row, 4, w)

        count = len(candidates)
        if total_size >= 1024:
            size_str = f"{total_size / 1024:.1f} GB"
        else:
            size_str = f"{total_size:.0f} MB"

        if count == 0:
            self._cleanup_info.setText("Keine Kandidaten gefunden — alle Modelle sind kürzlich genutzt.")
        else:
            self._cleanup_info.setText(
                f"{count} Modell(e) vorgeschlagen — mögliche Einsparung: {size_str}"
            )

        self._delete_all_btn.setEnabled(count > 0)

    # ──────────────────────────────────────────────────────────────────────
    # Scan-Logik
    # ──────────────────────────────────────────────────────────────────────

    def _start_scan(self):
        """Startet den Hintergrund-Scan."""
        if self._scan_thread and self._scan_thread.isRunning():
            return

        self._refresh_btn.setEnabled(False)
        self._status_lbl.setText("Scanne installierte Modelle...")

        self._scan_thread = QThread()
        self._scan_worker = _ScanWorker(ollama_url=self.ollama_url)
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(lambda: self._refresh_btn.setEnabled(True))

        self._scan_thread.start()

        # Ollama-Status parallel prüfen
        self._check_ollama_status()

    def _check_ollama_status(self):
        """Prüft Ollama-Verfügbarkeit und aktualisiert Status-Label."""
        import urllib.request
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/version")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    import json
                    data = json.loads(resp.read())
                    version = data.get("version", "?")
                    self._ollama_status_lbl.setText(f"Ollama v{version} ✓")
                    self._ollama_status_lbl.setStyleSheet(f"color: {OK}; font-size: 11px;")
                    return
        except (OSError, ValueError) as exc:
            logger.warning("_check_ollama_status: failed to reach Ollama: %s", exc)
        self._ollama_status_lbl.setText("Ollama: nicht erreichbar ✗")
        self._ollama_status_lbl.setStyleSheet(f"color: {ERR}; font-size: 11px;")

    def _on_scan_finished(self, entries: list):
        """Wird aufgerufen wenn Scan abgeschlossen."""
        if not self.isVisible():
            return
        self._entries = entries
        self._populate_installed_table(entries)
        self._populate_dl_tables()
        count = len(entries)
        self._status_lbl.setText(f"{count} Modelle gefunden.")
        logger.info("Model-Manager Scan abgeschlossen: %d Modelle.", count)

    def _on_scan_error(self, error: str):
        if not self.isVisible():
            return
        self._status_lbl.setText(f"Scan-Fehler: {error}")
        logger.error("Model-Manager Scan-Fehler: %s", error)
        self._refresh_btn.setEnabled(True)

    # ──────────────────────────────────────────────────────────────────────
    # Download-Logik
    # ──────────────────────────────────────────────────────────────────────

    def _on_pull_ollama(self, model_id: str):
        """Startet Ollama-Pull."""
        self._start_download(model_id, "ollama")

    def _on_download_hf(self, repo_id: str):
        """Startet HF-Download."""
        self._start_download(repo_id, "huggingface")

    def _on_custom_ollama_pull(self):
        model = self._custom_ollama_input.text().strip()
        if model:
            self._start_download(model, "ollama")

    def _on_custom_hf_download(self):
        repo = self._custom_hf_input.text().strip()
        if repo:
            self._start_download(repo, "huggingface")

    def _start_download(self, model_id: str, source: str):
        """Startet einen Download und zeigt Progress-Widget."""
        from services.model_lifecycle_service import get_model_lifecycle_service

        svc = get_model_lifecycle_service(self.ollama_url)

        # Progress-Row erstellen
        row_widget = self._add_progress_row(model_id)
        self._no_downloads_lbl.setVisible(False)

        # Relay für Thread-sicheres Signal
        relay = _ProgressRelay()
        relay.update.connect(lambda p: self._on_progress_update(p, row_widget))
        self._progress_relays[model_id] = relay

        def _cb(prog):
            relay.update.emit(prog)

        if source == "ollama":
            ok = svc.pull_ollama_model(model_id, progress_cb=_cb)
        else:
            ok = svc.download_hf_model(model_id, progress_cb=_cb)

        if not ok:
            self._status_lbl.setText(f"Download für '{model_id}' konnte nicht gestartet werden.")

    def _add_progress_row(self, model_id: str) -> QFrame:
        """Erstellt ein Progress-Widget für einen Download."""
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {BG2}; border: 1px solid {BG3}; border-radius: 4px; }}")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_l = QHBoxLayout()
        name_lbl = QLabel(f"⬇ {model_id}")
        name_lbl.setStyleSheet(f"font-weight: bold; color: {T1};")
        header_l.addWidget(name_lbl)
        header_l.addStretch()

        cancel_btn = QPushButton("✗")
        cancel_btn.setFixedSize(20, 20)
        cancel_btn.setStyleSheet(f"background: {BG3}; color: {T2}; border: none;")
        cancel_btn.setToolTip("Download abbrechen")
        cancel_btn.clicked.connect(lambda: self._on_cancel_download(model_id))
        header_l.addWidget(cancel_btn)
        layout.addLayout(header_l)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFixedHeight(14)
        layout.addWidget(progress_bar)

        status_lbl = QLabel("Startet...")
        status_lbl.setStyleSheet(f"color: {T3}; font-size: 10px;")
        layout.addWidget(status_lbl)

        # Refs für spätere Updates speichern
        frame.setProperty("progress_bar", progress_bar)
        frame.setProperty("status_lbl", status_lbl)
        frame.setProperty("model_id", model_id)

        self._progress_layout.addWidget(frame)
        self._tabs.setCurrentIndex(1)  # Tab "Download" aktivieren

        return frame

    def _on_progress_update(self, prog, row_widget: QFrame):
        """Aktualisiert Progress-Widget."""
        progress_bar: QProgressBar = row_widget.property("progress_bar")
        status_lbl: QLabel = row_widget.property("status_lbl")

        if progress_bar is None or status_lbl is None:
            return

        pct = int(prog.progress * 100)
        progress_bar.setValue(pct)

        if prog.error:
            status_lbl.setText(f"Fehler: {prog.error[:80]}")
            status_lbl.setStyleSheet(f"color: {ERR}; font-size: 10px;")
        elif prog.finished and not prog.error:
            progress_bar.setValue(100)
            status_lbl.setText("Download abgeschlossen ✓")
            status_lbl.setStyleSheet(f"color: {OK}; font-size: 10px;")
            # Nach 3s entfernen
            QTimer.singleShot(3000, lambda: self._remove_progress_row(row_widget, prog.model_id))
            # Scan neu starten
            QTimer.singleShot(500, self._start_scan)
        else:
            # Speed/ETA anzeigen
            status_parts = [prog.status]
            if prog.speed_mbps > 0:
                status_parts.append(f"{prog.speed_mbps:.1f} MB/s")
            if prog.eta_sec > 0:
                m, s = divmod(prog.eta_sec, 60)
                status_parts.append(f"ETA: {m}:{s:02d}")
            status_lbl.setText(" | ".join(status_parts))

    def _remove_progress_row(self, widget: QFrame, model_id: str):
        """Entfernt ein Progress-Widget."""
        self._progress_layout.removeWidget(widget)
        widget.deleteLater()
        self._progress_relays.pop(model_id, None)

        # Wenn keine Downloads mehr, Hinweis zeigen
        active = [w for w in self._progress_layout.children()
                  if isinstance(w, QFrame)]
        if not active:
            self._no_downloads_lbl.setVisible(True)

    def _on_cancel_download(self, model_id: str):
        """Bricht einen Download ab."""
        from services.model_lifecycle_service import get_model_lifecycle_service
        svc = get_model_lifecycle_service(self.ollama_url)
        svc.cancel_download(model_id)
        self._status_lbl.setText(f"Download '{model_id}' abgebrochen.")

    # ──────────────────────────────────────────────────────────────────────
    # Cleanup-Logik
    # ──────────────────────────────────────────────────────────────────────

    def _on_cleanup_scan(self):
        """Führt Cleanup-Analyse durch."""
        from services.model_lifecycle_service import get_model_lifecycle_service
        svc = get_model_lifecycle_service(self.ollama_url)
        days = self._days_spin.value()
        candidates = svc.get_cleanup_candidates(days_unused=days)
        self._populate_cleanup_table(candidates)

    def _on_delete_all_selected(self):
        """Löscht alle vorgeschlagenen Modelle nach Bestätigung."""
        rows = self._cleanup_table.rowCount()
        if rows == 0:
            return

        reply = QMessageBox.question(
            self,
            "Modelle löschen",
            f"Wirklich {rows} Modell(e) löschen? Diese Aktion kann nicht rückgängig gemacht werden.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        from services.model_lifecycle_service import get_model_lifecycle_service
        svc = get_model_lifecycle_service(self.ollama_url)

        deleted = 0
        for row in range(rows):
            name_item = self._cleanup_table.item(row, 0)
            source_item = self._cleanup_table.item(row, 1)
            if name_item and source_item:
                model_id = name_item.text()
                source = source_item.text().lower()
                if source == "ollama":
                    svc.delete_ollama_model(model_id)
                else:
                    svc.delete_hf_model(model_id)
                deleted += 1

        self._status_lbl.setText(f"{deleted} Modell(e) gelöscht.")
        QTimer.singleShot(500, self._start_scan)
        self._cleanup_table.setRowCount(0)
        self._cleanup_info.setText(f"{deleted} Modell(e) gelöscht.")

    # ──────────────────────────────────────────────────────────────────────
    # Löschen (Einzel)
    # ──────────────────────────────────────────────────────────────────────

    def _on_delete_model(self, model_id: str, source: str):
        """Löscht ein einzelnes Modell nach Bestätigung."""
        reply = QMessageBox.question(
            self,
            "Modell löschen",
            f"Modell '{model_id}' wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        from services.model_lifecycle_service import get_model_lifecycle_service
        svc = get_model_lifecycle_service(self.ollama_url)

        if source == "ollama":
            ok = svc.delete_ollama_model(model_id)
        else:
            ok = svc.delete_hf_model(model_id)

        if ok:
            self._status_lbl.setText(f"'{model_id}' gelöscht.")
            QTimer.singleShot(300, self._start_scan)
        else:
            self._status_lbl.setText(f"Fehler beim Löschen von '{model_id}'.")
