"""DELIVER Workspace: Export settings + preview + protokoll.

P9-Step5: 3 Sub-Tabs (EXPORT | VORSCHAU | PROTOKOLL).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QPushButton, QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt

from ui.widgets.workflow_components import SectionTabs, StatusStrip, make_expert_container


class DeliverWorkspace(QWidget):
    """Deliver workspace — 3 Sub-Tabs (Export / Vorschau / Protokoll)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._tabs = SectionTabs()
        self._tabs.setToolTip(
            "Deliver-Bereich: Exportdatei und Renderparameter einstellen."
        )
        self._tabs.addTab(self._build_export_tab(), "EXPORT")
        self._tabs.setTabToolTip(0, "Exportdatei, Aufloesung, FPS und Render-Preset einstellen.")
        layout.addWidget(self._tabs)

        self.deliver_status = StatusStrip("Export bereit, sobald eine Timeline vorhanden ist.")
        layout.addWidget(self.deliver_status)

        self.expert_tools = make_expert_container(self)
        self.expert_tools_tabs = SectionTabs(self.expert_tools)
        self.expert_tools_tabs.addTab(self._build_preview_tab(), "VORSCHAU")
        self.expert_tools_tabs.addTab(self._build_protokoll_tab(), "PROTOKOLL")
        self.expert_tools.layout().addWidget(self.expert_tools_tabs)

        # Tab-Order
        self.setTabOrder(self.export_name_input, self.resolution_combo)
        self.setTabOrder(self.resolution_combo, self.fps_combo)
        self.setTabOrder(self.fps_combo, self.preset_combo)
        self.setTabOrder(self.preset_combo, self.btn_refresh_production)
        self.setTabOrder(self.btn_refresh_production, self.btn_preview)
        self.setTabOrder(self.btn_preview, self.btn_export)
        self.setTabOrder(self.btn_export, self.btn_preview_play)
        self.setTabOrder(self.btn_preview_play, self.btn_preview_stop)

    # ------------------------------------------------------------------
    def _build_export_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(8)

        # Timeline-Status
        info_group = QGroupBox("Timeline-Status")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(8, 4, 8, 4)
        self.production_info = QLabel("Timeline laden...")
        self.production_info.setStyleSheet("color: #e8e6e3; font-size: 11px;")
        self.production_info.setToolTip(
            "Zeigt eine Zusammenfassung der aktuellen Timeline: "
            "Anzahl der Clips, Spuren und geschaetzte Gesamtdauer"
        )
        info_layout.addWidget(self.production_info)
        v.addWidget(info_group)

        # Settings
        settings_group = QGroupBox("Export-Einstellungen")
        settings_grid = QVBoxLayout(settings_group)
        settings_grid.setContentsMargins(8, 4, 8, 4)
        settings_grid.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("Dateiname:"))
        self.export_name_input = QLineEdit("output.mp4")
        self.export_name_input.setFixedHeight(22)
        self.export_name_input.setAccessibleName("Export Dateiname")
        self.export_name_input.setToolTip(
            "Dateiname fuer Export im Projekt-Ausgabeordner. Beispiel: dj_set_final.mp4."
        )
        row1.addWidget(self.export_name_input, stretch=2)
        row1.addWidget(QLabel("Aufloesung:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1920x1080", "1280x720", "854x480", "3840x2160"])
        self.resolution_combo.setFixedHeight(22)
        self.resolution_combo.setAccessibleName("Export Aufloesung")
        self.resolution_combo.setToolTip(
            "Export-Aufloesung. Hoehere Werte brauchen mehr Renderzeit und Speicherplatz."
        )
        row1.addWidget(self.resolution_combo, stretch=1)
        settings_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "24", "25", "60"])
        self.fps_combo.setFixedHeight(22)
        self.fps_combo.setAccessibleName("Export Bildrate")
        self.fps_combo.setToolTip(
            "Export-Bildrate. Nutze meist dieselbe FPS wie Projekt oder Zielplattform."
        )
        row2.addWidget(self.fps_combo, stretch=1)
        row2.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Standard (H.264 fast)", "Hohe Qualitaet (H.264 slow)", "Draft (schnell)"])
        self.preset_combo.setFixedHeight(22)
        self.preset_combo.setAccessibleName("Export Preset")
        self.preset_combo.setToolTip(
            "Render-Preset: Draft fuer schnelle Kontrolle, hohe Qualitaet fuer finalen Export."
        )
        row2.addWidget(self.preset_combo, stretch=2)
        settings_grid.addLayout(row2)

        v.addWidget(settings_group)

        # Estimate
        self.render_estimate_label = QLabel("Geschaetzte Renderzeit: —")
        self.render_estimate_label.setStyleSheet("color: #9ca3af; font-size: 10px; padding: 0 8px;")
        v.addWidget(self.render_estimate_label)

        # Action-Row
        export_row = QHBoxLayout()
        export_row.setSpacing(6)
        self.btn_preview = QPushButton("Quick-Preview (10s)")
        self.btn_preview.setFixedHeight(28)
        self.btn_preview.setMaximumWidth(180)
        self.btn_preview.setAccessibleName("Quick-Preview rendern")
        self.btn_preview.setToolTip(
            "Kurze 10-Sekunden-Vorschau rendern, um Schnitt, Look und Audio schnell zu pruefen."
        )
        export_row.addWidget(self.btn_preview)

        self.btn_export = QPushButton("Video exportieren")
        self.btn_export.setObjectName("btn_accent")
        self.btn_export.setFixedHeight(28)
        self.btn_export.setMaximumWidth(180)
        self.btn_export.setAccessibleName("Finales Video exportieren")
        self.btn_export.setToolTip(
            "Finales Video mit den aktuellen Timeline- und Export-Einstellungen rendern."
        )
        export_row.addWidget(self.btn_export)

        self.btn_refresh_production = QPushButton("Aktualisieren")
        self.btn_refresh_production.setFixedHeight(28)
        self.btn_refresh_production.setMaximumWidth(120)
        self.btn_refresh_production.setAccessibleName("Timeline-Status aktualisieren")
        self.btn_refresh_production.setToolTip(
            "Timeline-Zusammenfassung und Renderzeit-Schaetzung neu berechnen."
        )
        export_row.addWidget(self.btn_refresh_production)
        export_row.addStretch()
        v.addLayout(export_row)

        # Progress
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        self.export_progress.setFixedHeight(20)
        self.export_progress.setTextVisible(True)
        v.addWidget(self.export_progress)
        v.addStretch(1)
        return page

    # ------------------------------------------------------------------
    def _build_preview_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        # Preview-Video Bereich
        wrap = QHBoxLayout()
        wrap.addStretch()
        self.preview_video_label = QLabel("Keine Vorschau")
        self.preview_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_video_label.setFixedSize(960, 540)
        self.preview_video_label.setStyleSheet(
            "background-color: #1a1a2e; color: #6b7280; "
            "border: 1px solid #374151; border-radius: 4px;"
        )
        wrap.addWidget(self.preview_video_label)
        wrap.addStretch()
        v.addLayout(wrap)

        # Playback-Controls
        controls = QHBoxLayout()
        controls.addStretch()
        self.btn_preview_play = QPushButton("Play")
        self.btn_preview_play.setFixedHeight(26)
        self.btn_preview_play.setFixedWidth(72)
        self.btn_preview_play.setEnabled(False)
        self.btn_preview_play.setAccessibleName("Vorschau abspielen")
        self.btn_preview_play.setToolTip(
            "Gerenderte Vorschau abspielen oder fortsetzen. Erst aktiv, wenn eine Vorschau vorhanden ist."
        )
        controls.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("Stop")
        self.btn_preview_stop.setFixedHeight(26)
        self.btn_preview_stop.setFixedWidth(72)
        self.btn_preview_stop.setEnabled(False)
        self.btn_preview_stop.setAccessibleName("Vorschau stoppen")
        self.btn_preview_stop.setToolTip(
            "Vorschau stoppen und Wiedergabe zuruecksetzen."
        )
        controls.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("0:00 / 0:00")
        self.preview_time_label.setStyleSheet("color: #9ca3af; font-size: 10px; padding: 0 8px;")
        controls.addWidget(self.preview_time_label)
        controls.addStretch()
        v.addLayout(controls)
        v.addStretch(1)
        return page

    # ------------------------------------------------------------------
    def _build_protokoll_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)

        log_lbl = QLabel("EXPORT-PROTOKOLL")
        log_lbl.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(log_lbl)

        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setVisible(False)
        self.export_log.setStyleSheet(
            "background-color: #0a0d12; border: 1px solid rgba(255,255,255,15);"
            " color: #e8e6e3; font-family: 'Consolas'; font-size: 10px;"
        )
        self.export_log.setAccessibleName("Export Protokoll")
        self.export_log.setToolTip(
            "Export-Protokoll mit Renderfortschritt, FFmpeg-Meldungen und Fehlerdetails."
        )
        v.addWidget(self.export_log, stretch=1)
        return page
