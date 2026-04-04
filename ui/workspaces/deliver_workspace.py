"""DELIVER Workspace: Export settings and rendering."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QPushButton, QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt


class DeliverWorkspace(QWidget):
    """Export workspace — timeline status, export settings, progress log.

    Signal wiring is done by PBWindow after construction.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        # Timeline-Status
        info_group = QGroupBox("Timeline-Status")
        info_layout = QVBoxLayout(info_group)
        self.production_info = QLabel("Timeline laden...")
        self.production_info.setStyleSheet("color: #e8e6e3; font-size: 14px;")
        self.production_info.setToolTip(
            "Zeigt eine Zusammenfassung der aktuellen Timeline: "
            "Anzahl der Clips, Spuren und geschaetzte Gesamtdauer"
        )
        info_layout.addWidget(self.production_info)
        info_layout.addStretch()
        layout.addWidget(info_group)

        # Export-Einstellungen
        settings_group = QGroupBox("Export-Einstellungen")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        name_label = QLabel("Dateiname:")
        name_label.setToolTip("Name der finalen Video-Datei")
        settings_layout.addWidget(name_label)
        self.export_name_input = QLineEdit("output.mp4")
        self.export_name_input.setToolTip("Gib den gewuenschten Dateinamen fuer das exportierte Video ein")
        self.export_name_input.setAccessibleName("Export Dateiname")
        self.export_name_input.setStatusTip("Dateiname fuer das exportierte Video eingeben (z.B. output.mp4)")
        settings_layout.addWidget(self.export_name_input)

        res_label = QLabel("Aufloesung:")
        settings_layout.addWidget(res_label)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1920x1080", "1280x720", "854x480", "3840x2160"])
        self.resolution_combo.setToolTip("Waehle die Video-Aufloesung")
        self.resolution_combo.setAccessibleName("Export Aufloesung")
        self.resolution_combo.setStatusTip("Aufloesung des exportierten Videos waehlen")
        settings_layout.addWidget(self.resolution_combo)

        fps_label = QLabel("FPS:")
        settings_layout.addWidget(fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "24", "25", "60"])
        self.fps_combo.setToolTip("Waehle die Bildrate")
        self.fps_combo.setAccessibleName("Export Bildrate")
        self.fps_combo.setStatusTip("Bildrate (FPS) des exportierten Videos waehlen")
        settings_layout.addWidget(self.fps_combo)

        preset_label = QLabel("Preset:")
        settings_layout.addWidget(preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Standard (H.264 fast)", "Hohe Qualitaet (H.264 slow)", "Draft (schnell)"])
        self.preset_combo.setToolTip(
            "Waehle ein Export-Preset:\n"
            "- Standard: Gute Qualitaet, mittlere Geschwindigkeit\n"
            "- Hohe Qualitaet: Beste Qualitaet, langsamer\n"
            "- Draft: Schnelle Vorschau, niedrigere Qualitaet"
        )
        self.preset_combo.setAccessibleName("Export Preset")
        self.preset_combo.setStatusTip("Qualitaets-Preset fuer den Video-Export waehlen")
        settings_layout.addWidget(self.preset_combo)

        settings_layout.addStretch()

        layout.addWidget(settings_group)

        # Render-Schaetzung
        estimate_row = QHBoxLayout()
        estimate_row.setSpacing(10)
        self.render_estimate_label = QLabel("Geschaetzte Renderzeit: —")
        self.render_estimate_label.setStyleSheet("color: #9ca3af; font-size: 13px;")
        self.render_estimate_label.setToolTip(
            "Geschaetzte Dauer fuer den kompletten Export basierend auf "
            "Timeline-Laenge, Aufloesung und Effekten"
        )
        estimate_row.addWidget(self.render_estimate_label)
        estimate_row.addStretch()
        layout.addLayout(estimate_row)

        # Export-Buttons + Preview-Button
        export_row = QHBoxLayout()
        export_row.setSpacing(10)

        self.btn_preview = QPushButton("Quick-Preview (10s)")
        self.btn_preview.setFixedHeight(35)
        self.btn_preview.setMaximumWidth(300)
        self.btn_preview.setToolTip(
            "Rendert eine Vorschau der ersten 10 Sekunden der Timeline "
            "und spielt sie im Preview-Widget ab"
        )
        self.btn_preview.setAccessibleName("Quick-Preview rendern")
        self.btn_preview.setStatusTip("Rendert eine 10-Sekunden-Vorschau der Timeline mit FFmpeg")
        export_row.addWidget(self.btn_preview)

        self.btn_export = QPushButton("Video exportieren")
        self.btn_export.setObjectName("btn_accent")
        self.btn_export.setFixedHeight(35)
        self.btn_export.setMaximumWidth(300)
        self.btn_export.setToolTip("Finales Video mit FFmpeg rendern")
        self.btn_export.setAccessibleName("Finales Video exportieren")
        self.btn_export.setStatusTip("Startet den finalen Video-Export mit den gewaehlten Einstellungen")
        export_row.addWidget(self.btn_export)

        self.btn_refresh_production = QPushButton("Aktualisieren")
        self.btn_refresh_production.setFixedHeight(35)
        self.btn_refresh_production.setMaximumWidth(300)
        self.btn_refresh_production.setToolTip("Timeline-Status aktualisieren")
        self.btn_refresh_production.setAccessibleName("Timeline-Status aktualisieren")
        self.btn_refresh_production.setStatusTip("Timeline-Status und Clip-Anzahl neu laden")
        export_row.addWidget(self.btn_refresh_production)

        export_row.addStretch()

        layout.addLayout(export_row)

        # Export-Fortschritt
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        self.export_progress.setTextVisible(True)
        self.export_progress.setToolTip("Fortschritt des aktuellen Video-Exports")
        layout.addWidget(self.export_progress)

        # Preview-Video Bereich
        preview_group = QGroupBox("Export-Vorschau")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_video_label = QLabel("Keine Vorschau")
        self.preview_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_video_label.setMinimumHeight(180)
        self.preview_video_label.setMaximumHeight(300)
        self.preview_video_label.setStyleSheet(
            "background-color: #1a1a2e; color: #6b7280; "
            "border: 1px solid #374151; border-radius: 4px;"
        )
        self.preview_video_label.setToolTip(
            "Hier wird die gerenderte Vorschau der ersten 10 Sekunden angezeigt"
        )
        preview_layout.addWidget(self.preview_video_label)

        # Preview playback controls
        preview_controls = QHBoxLayout()
        self.btn_preview_play = QPushButton("Play")
        self.btn_preview_play.setFixedHeight(28)
        self.btn_preview_play.setMaximumWidth(80)
        self.btn_preview_play.setEnabled(False)
        self.btn_preview_play.setToolTip("Preview abspielen / pausieren")
        self.btn_preview_play.setAccessibleName("Vorschau abspielen")
        self.btn_preview_play.setStatusTip("Export-Vorschau abspielen oder pausieren")
        preview_controls.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("Stop")
        self.btn_preview_stop.setFixedHeight(28)
        self.btn_preview_stop.setMaximumWidth(80)
        self.btn_preview_stop.setEnabled(False)
        self.btn_preview_stop.setToolTip("Preview-Wiedergabe stoppen")
        self.btn_preview_stop.setAccessibleName("Vorschau stoppen")
        self.btn_preview_stop.setStatusTip("Export-Vorschau stoppen")
        preview_controls.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("0:00 / 0:00")
        self.preview_time_label.setStyleSheet("color: #9ca3af;")
        preview_controls.addWidget(self.preview_time_label)
        preview_controls.addStretch()
        preview_layout.addLayout(preview_controls)

        layout.addWidget(preview_group)

        # Export-Log
        log_label = QLabel("Export-Protokoll:")
        log_label.setStyleSheet("color: #9ca3af; font-weight: 600; margin-top: 8px;")
        layout.addWidget(log_label)

        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setToolTip("Protokoll des Export-Vorgangs")
        self.export_log.setAccessibleName("Export Protokoll")
        layout.addWidget(self.export_log, stretch=1)

        # Tab order: settings → export controls → preview controls
        self.setTabOrder(self.export_name_input, self.resolution_combo)
        self.setTabOrder(self.resolution_combo, self.fps_combo)
        self.setTabOrder(self.fps_combo, self.preset_combo)
        self.setTabOrder(self.preset_combo, self.btn_refresh_production)
        self.setTabOrder(self.btn_refresh_production, self.btn_preview)
        self.setTabOrder(self.btn_preview, self.btn_export)
        self.setTabOrder(self.btn_export, self.btn_preview_play)
        self.setTabOrder(self.btn_preview_play, self.btn_preview_stop)
