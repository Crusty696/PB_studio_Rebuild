"""DELIVER Workspace: Export settings and rendering."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QPushButton, QProgressBar, QTextEdit,
)


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
        settings_layout.addWidget(self.export_name_input)

        res_label = QLabel("Aufloesung:")
        settings_layout.addWidget(res_label)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1920x1080", "1280x720", "854x480", "3840x2160"])
        self.resolution_combo.setToolTip("Waehle die Video-Aufloesung")
        settings_layout.addWidget(self.resolution_combo)

        fps_label = QLabel("FPS:")
        settings_layout.addWidget(fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "24", "25", "60"])
        self.fps_combo.setToolTip("Waehle die Bildrate")
        settings_layout.addWidget(self.fps_combo)
        settings_layout.addStretch()

        layout.addWidget(settings_group)

        # Export-Buttons
        export_row = QHBoxLayout()
        export_row.setSpacing(10)

        self.btn_export = QPushButton("Video exportieren")
        self.btn_export.setObjectName("btn_accent")
        self.btn_export.setFixedHeight(35)
        self.btn_export.setMaximumWidth(300)
        self.btn_export.setToolTip("Finales Video mit FFmpeg rendern")
        export_row.addWidget(self.btn_export)

        self.btn_refresh_production = QPushButton("Aktualisieren")
        self.btn_refresh_production.setFixedHeight(35)
        self.btn_refresh_production.setMaximumWidth(300)
        self.btn_refresh_production.setToolTip("Timeline-Status aktualisieren")
        export_row.addWidget(self.btn_refresh_production)

        export_row.addStretch()

        layout.addLayout(export_row)

        # Export-Fortschritt
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        self.export_progress.setTextVisible(True)
        self.export_progress.setToolTip("Fortschritt des aktuellen Video-Exports")
        layout.addWidget(self.export_progress)

        # Export-Log
        log_label = QLabel("Export-Protokoll:")
        log_label.setStyleSheet("color: #9ca3af; font-weight: 600; margin-top: 8px;")
        layout.addWidget(log_label)

        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setToolTip("Protokoll des Export-Vorgangs")
        layout.addWidget(self.export_log, stretch=1)
