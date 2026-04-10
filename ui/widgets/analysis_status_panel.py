"""Analysis Status Panel Widget — VAD-44.

PySide6-Widget zur Anzeige und Steuerung des Analyse-Status pro Medien-Datei.
Zeigt alle definierten Analyse-Schritte (VIDEO_STEPS / AUDIO_STEPS) mit:
- Status-Icons und Farbcodierung (grün/gelb/rot/grau)
- Fortschrittsbalken (Gesamtfortschritt)
- Klickbare Zeilen zum Starten einzelner Analysen
- Integration mit AnalysisStatusService

Siehe Plan: VAD-36 (Daten-Analyse Status Dashboard)
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QFrame, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor, QBrush, QFont, QKeySequence, QShortcut

from services import analysis_status_service
from database import AnalysisStatus

logger = logging.getLogger(__name__)

# Status icons
STATUS_ICONS = {
    "done": "✓",
    "running": "⟳",
    "error": "✗",
    "pending": "○",
}

# Status colors (RGB)
STATUS_COLORS = {
    "done": QColor(74, 222, 128),      # Green
    "running": QColor(212, 164, 74),   # Yellow/Gold
    "error": QColor(239, 68, 68),      # Red
    "pending": QColor(156, 163, 175),  # Gray
}

# Readable step names (German)
STEP_NAMES = {
    # Video steps
    "metadata_extract": "Metadaten",
    "scene_detection": "Szenen-Erkennung",
    "motion_scores": "Motion-Analyse",
    "keyframe_extraction": "Keyframe-Export",
    "siglip_embeddings": "Visual Embeddings",
    "vector_db_storage": "Vector DB",
    "ai_scene_caption": "AI Captioning",
    "scene_db_storage": "Scene DB",
    # Audio steps
    "bpm_detection": "BPM & Beats",
    "waveform_analysis": "Waveform",
    "key_detection": "Tonart",
    "lufs_analysis": "LUFS Loudness",
    "mood_genre_classify": "Mood/Genre",
    "spectral_analysis": "Spektral-Analyse",
    "structure_detection": "Song-Struktur",
    "stem_separation": "Stem-Separation",
}


class AnalysisStatusPanel(QWidget):
    """Panel zur Anzeige des Analyse-Status einer einzelnen Medien-Datei.

    Signals:
        analysis_requested: (step_key: str) - User hat Analyse-Start angefordert
    """

    analysis_requested = Signal(str)  # step_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media_type: Optional[str] = None
        self._media_id: Optional[int] = None
        self._filter_mode: str = "all"  # "all", "pending", "error"
        self._build_ui()
        self._setup_shortcuts()

    def _build_ui(self):
        """Erstellt das UI-Layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QLabel("Analyse-Status")
        header.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 12px; "
            "letter-spacing: 1.5px; text-transform: uppercase;"
        )
        layout.addWidget(header)

        # File info label
        self.file_info_label = QLabel("Keine Datei ausgewählt")
        self.file_info_label.setStyleSheet(
            "color: #9ca3af; font-size: 11px; padding: 4px 0px;"
        )
        layout.addWidget(self.file_info_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v/%m Schritte)")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #1a2030;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                color: #f9fafb;
                text-align: center;
                font-size: 10px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d4a44a, stop:1 #f0c866);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 4, 0, 0)
        filter_row.setSpacing(8)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #9ca3af; font-size: 10px; font-weight: 600;")
        filter_row.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Alle", "Nur Ausstehend", "Nur Fehler"])
        self.filter_combo.setFixedHeight(24)
        self.filter_combo.setFixedWidth(140)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background: #1a2030;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                color: #e5e7eb;
                font-size: 10px;
                padding: 2px 8px;
            }
            QComboBox:hover {
                border-color: #d4a44a;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #9ca3af;
                margin-right: 8px;
            }
        """)
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch()

        layout.addLayout(filter_row)

        # Status table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Status", "Schritt", "Wert", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(3, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #161c26;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
                gridline-color: rgba(255,255,255,0.05);
            }
            QTableWidget::item {
                padding: 4px 8px;
                color: #e5e7eb;
            }
            QTableWidget::item:selected {
                background: rgba(212,164,74,0.15);
                color: #f0c866;
            }
            QHeaderView::section {
                background: #1a2030;
                color: #9ca3af;
                padding: 6px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
            }
        """)
        layout.addWidget(self.table, stretch=1)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 4, 0, 0)

        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #1a2030;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                color: #e5e7eb;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #283040;
                border-color: #d4a44a;
                color: #f0c866;
            }
        """)
        actions_layout.addWidget(self.btn_refresh)

        self.btn_retry_errors = QPushButton("Alle Fehler wiederholen")
        self.btn_retry_errors.setFixedHeight(32)
        self.btn_retry_errors.clicked.connect(self._on_retry_all_errors)
        self.btn_retry_errors.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.15);
                border: 1px solid #ef4444;
                border-radius: 4px;
                color: #fca5a5;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: rgba(239,68,68,0.25);
                color: #fef2f2;
            }
            QPushButton:disabled {
                background: rgba(75,85,99,0.15);
                border-color: #4b5563;
                color: #6b7280;
            }
        """)
        self.btn_retry_errors.setEnabled(False)  # Will be enabled when errors exist
        actions_layout.addWidget(self.btn_retry_errors)

        actions_layout.addStretch()

        layout.addLayout(actions_layout)

    def set_media(self, media_type: str, media_id: int, title: str = ""):
        """Setzt die anzuzeigende Medien-Datei.

        Args:
            media_type: "video" oder "audio"
            media_id: ID der VideoClip oder AudioTrack
            title: Optional - Dateiname für Anzeige
        """
        self._media_type = media_type
        self._media_id = media_id

        # Update file info
        media_type_label = "Video" if media_type == "video" else "Audio"
        if title:
            self.file_info_label.setText(f"{media_type_label}: {title}")
        else:
            self.file_info_label.setText(f"{media_type_label} ID {media_id}")

        # Load and display
        self.refresh()

    def refresh(self):
        """Lädt den aktuellen Status aus der DB und aktualisiert die Anzeige."""
        if self._media_type is None or self._media_id is None:
            self._clear_display()
            return

        # Infer status from DB first (for migration/backwards compat)
        try:
            analysis_status_service.infer_from_db(self._media_type, self._media_id)
        except Exception as e:
            logger.warning("infer_from_db failed: %s", e)

        # Get status
        status_dict = analysis_status_service.get_status(self._media_type, self._media_id)

        # Get steps for this media type
        if self._media_type == "video":
            steps = analysis_status_service.VIDEO_STEPS
        elif self._media_type == "audio":
            steps = analysis_status_service.AUDIO_STEPS
        else:
            steps = []

        # Apply filter
        filtered_steps = []
        error_count = 0

        for step_key in steps:
            status_entry = status_dict.get(step_key)
            status = status_entry.status if status_entry else "pending"

            # Track errors for button state
            if status == "error":
                error_count += 1

            # Apply filter
            if self._filter_mode == "pending" and status != "pending":
                continue
            elif self._filter_mode == "error" and status != "error":
                continue

            filtered_steps.append(step_key)

        # Update table
        self.table.setRowCount(len(filtered_steps))
        completed_count = 0

        for row_idx, step_key in enumerate(filtered_steps):
            status_entry = status_dict.get(step_key)

            if status_entry:
                status = status_entry.status
                value_summary = status_entry.value_summary or {}
                error_msg = status_entry.error_message
            else:
                status = "pending"
                value_summary = {}
                error_msg = None

            if status == "done":
                completed_count += 1

            # Column 0: Status icon
            icon_item = QTableWidgetItem(STATUS_ICONS.get(status, "?"))
            icon_item.setForeground(QBrush(STATUS_COLORS.get(status, QColor(255, 255, 255))))
            icon_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setPointSize(14)
            font.setBold(True)
            icon_item.setFont(font)
            icon_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row_idx, 0, icon_item)

            # Column 1: Step name
            step_name = STEP_NAMES.get(step_key, step_key)
            name_item = QTableWidgetItem(step_name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row_idx, 1, name_item)

            # Column 2: Value summary
            if error_msg:
                value_text = f"Fehler: {error_msg[:40]}..."
                value_color = STATUS_COLORS["error"]
            elif value_summary:
                value_text = self._format_value_summary(value_summary)
                value_color = QColor(156, 163, 175)  # Gray
            else:
                value_text = "—"
                value_color = QColor(75, 85, 99)  # Darker gray

            value_item = QTableWidgetItem(value_text)
            value_item.setForeground(QBrush(value_color))
            value_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row_idx, 2, value_item)

            # Column 3: Action button (only for pending/error)
            if status in ("pending", "error"):
                btn = QPushButton("Starten" if status == "pending" else "Wiederholen")
                btn.setFixedHeight(24)
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(212,164,74,0.15);
                        border: 1px solid #d4a44a;
                        border-radius: 3px;
                        color: #f0c866;
                        font-size: 9px;
                        font-weight: 600;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background: rgba(212,164,74,0.25);
                    }
                """)
                # Store step_key in button property
                btn.setProperty("step_key", step_key)
                btn.clicked.connect(self._on_action_clicked)
                self.table.setCellWidget(row_idx, 3, btn)
            else:
                # Empty cell
                self.table.setItem(row_idx, 3, QTableWidgetItem(""))

        # Update progress bar
        total_steps = len(steps)
        self.progress_bar.setMaximum(total_steps)
        self.progress_bar.setValue(completed_count)

        # Enable/disable retry button based on error count
        self.btn_retry_errors.setEnabled(error_count > 0)
        if error_count > 0:
            self.btn_retry_errors.setText(f"Alle Fehler wiederholen ({error_count})")
        else:
            self.btn_retry_errors.setText("Alle Fehler wiederholen")

    def _format_value_summary(self, summary: dict) -> str:
        """Formatiert value_summary für Anzeige."""
        if not summary:
            return "—"

        # Pick most relevant fields
        parts = []
        if "bpm" in summary:
            parts.append(f"{summary['bpm']:.1f} BPM")
        if "beats" in summary:
            parts.append(f"{summary['beats']} Beats")
        if "scenes" in summary:
            parts.append(f"{summary['scenes']} Szenen")
        if "resolution" in summary:
            parts.append(str(summary["resolution"]))
        if "key" in summary:
            parts.append(f"Key: {summary['key']}")
        if "lufs" in summary:
            parts.append(f"{summary['lufs']:.1f} LUFS")
        if "mood" in summary or "genre" in summary:
            mood_genre = "/".join(filter(None, [summary.get("mood"), summary.get("genre")]))
            if mood_genre:
                parts.append(mood_genre)

        if parts:
            return ", ".join(parts)

        # Fallback: first 2-3 key-value pairs
        items = list(summary.items())[:3]
        return ", ".join(f"{k}: {v}" for k, v in items)

    def _on_action_clicked(self):
        """Handler für Action-Button-Klicks."""
        sender = self.sender()
        if sender:
            step_key = sender.property("step_key")
            if step_key:
                logger.info("Analysis requested for step: %s", step_key)
                self.analysis_requested.emit(step_key)

    def _setup_shortcuts(self):
        """Richtet Tastatur-Shortcuts ein."""
        # F5 - Refresh
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self.refresh)

        # Ctrl+R - Refresh (alternative)
        refresh_alt_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_alt_shortcut.activated.connect(self.refresh)

    def _on_filter_changed(self, index: int):
        """Handler für Filter-Änderungen."""
        # Map combo index to filter mode
        filter_map = {0: "all", 1: "pending", 2: "error"}
        self._filter_mode = filter_map.get(index, "all")
        self.refresh()

    def _on_retry_all_errors(self):
        """Sendet analysis_requested Signal für alle fehlgeschlagenen Schritte."""
        if self._media_type is None or self._media_id is None:
            return

        # Get status
        status_dict = analysis_status_service.get_status(self._media_type, self._media_id)

        # Get steps for this media type
        if self._media_type == "video":
            steps = analysis_status_service.VIDEO_STEPS
        elif self._media_type == "audio":
            steps = analysis_status_service.AUDIO_STEPS
        else:
            return

        # Find all error steps
        error_steps = []
        for step_key in steps:
            status_entry = status_dict.get(step_key)
            if status_entry and status_entry.status == "error":
                error_steps.append(step_key)

        # Emit signal for each error step
        for step_key in error_steps:
            logger.info("Retrying error step: %s", step_key)
            self.analysis_requested.emit(step_key)

        if error_steps:
            logger.info("Retrying %d error steps", len(error_steps))

    def _clear_display(self):
        """Leert die Anzeige."""
        self.file_info_label.setText("Keine Datei ausgewählt")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.table.setRowCount(0)


class AnalysisStatusMiniWidget(QWidget):
    """Mini-Widget für MediaPool-Tabelle: zeigt nur Fortschrittsbalken."""

    def __init__(self, media_type: str, media_id: int, parent=None):
        super().__init__(parent)
        self._media_type = media_type
        self._media_id = media_id
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #0a0d12;
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 3px;
                color: #9ca3af;
                text-align: center;
                font-size: 8px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: #4ade80;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def refresh(self):
        """Aktualisiert den Fortschrittsbalken."""
        try:
            percent = analysis_status_service.get_completion_percent(
                self._media_type, self._media_id
            )
            self.progress_bar.setValue(int(percent))
        except Exception as e:
            logger.warning("Failed to get completion percent: %s", e)
            self.progress_bar.setValue(0)
