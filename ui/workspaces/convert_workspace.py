"""CONVERT Workspace: Video standardization and batch conversion."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QProgressBar, QTextEdit, QSplitter, QSlider,
)
from PySide6.QtCore import Qt

from ui.theme import BG0, T1


class ConvertWorkspace(QWidget):
    """Convert workspace — format settings, batch conversion, log.

    Signal wiring is done by PBWindow after construction.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Settings
        settings_panel = QWidget()
        settings_panel.setMaximumWidth(350)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setSpacing(8)

        format_group = QGroupBox("Ziel-Format")
        format_layout = QVBoxLayout(format_group)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Aufloesung:"))
        self.convert_resolution = QComboBox()
        self.convert_resolution.addItems([
            "1920x1080 (1080p)", "2560x1440 (2K)", "3840x2160 (4K)", "1280x720 (720p)"
        ])
        self.convert_resolution.setToolTip("Ziel-Aufloesung fuer alle Videos")
        res_row.addWidget(self.convert_resolution)
        format_layout.addLayout(res_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Framerate:"))
        self.convert_fps = QComboBox()
        self.convert_fps.addItems(["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"])
        self.convert_fps.setToolTip("Ziel-Framerate fuer alle Videos")
        fps_row.addWidget(self.convert_fps)
        format_layout.addLayout(fps_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Container:"))
        self.convert_format = QComboBox()
        self.convert_format.addItems([
            "mp4 (H.264)", "mp4 (H.265/HEVC)", "mov (ProRes)", "mkv (H.264)"
        ])
        self.convert_format.setToolTip("Ziel-Containerformat")
        fmt_row.addWidget(self.convert_format)
        format_layout.addLayout(fmt_row)
        format_layout.addStretch()

        settings_layout.addWidget(format_group)

        action_group = QGroupBox("Aktionen")
        action_layout = QVBoxLayout(action_group)

        self.btn_standardize_all = QPushButton("Alle Videos standardisieren")
        self.btn_standardize_all.setObjectName("btn_accent")
        self.btn_standardize_all.setFixedHeight(35)
        self.btn_standardize_all.setMaximumWidth(300)
        self.btn_standardize_all.setToolTip(
            "Konvertiert alle Videos im Video Pool in das gewaehlte Standardformat"
        )
        action_layout.addWidget(self.btn_standardize_all)

        self.convert_progress = QProgressBar()
        self.convert_progress.setVisible(False)
        self.convert_progress.setTextVisible(True)
        self.convert_progress.setFormat("Konvertierung...")
        action_layout.addWidget(self.convert_progress)
        action_layout.addStretch()

        settings_layout.addWidget(action_group)

        # ── Clip-Effekte ──────────────────────────────────
        effects_group = QGroupBox("Clip-Effekte")
        effects_layout = QVBoxLayout(effects_group)

        self.effects_clip_combo = QComboBox()
        self.effects_clip_combo.setToolTip("Timeline-Clip fuer Effekt-Bearbeitung waehlen")
        effects_layout.addWidget(self.effects_clip_combo)

        # Brightness
        br_row = QHBoxLayout()
        br_row.addWidget(QLabel("Helligkeit:"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setToolTip("Helligkeit (-1.0 bis +1.0)")
        br_row.addWidget(self.brightness_slider)
        self.brightness_label = QLabel("0")
        self.brightness_label.setFixedWidth(30)
        br_row.addWidget(self.brightness_label)
        effects_layout.addLayout(br_row)

        # Contrast
        ct_row = QHBoxLayout()
        ct_row.addWidget(QLabel("Kontrast:"))
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(0, 300)
        self.contrast_slider.setValue(100)
        self.contrast_slider.setToolTip("Kontrast (0.0 bis 3.0)")
        ct_row.addWidget(self.contrast_slider)
        self.contrast_label = QLabel("100")
        self.contrast_label.setFixedWidth(30)
        ct_row.addWidget(self.contrast_label)
        effects_layout.addLayout(ct_row)

        # Crossfade
        cf_row = QHBoxLayout()
        cf_row.addWidget(QLabel("Crossfade:"))
        self.crossfade_slider = QSlider(Qt.Orientation.Horizontal)
        self.crossfade_slider.setRange(0, 50)
        self.crossfade_slider.setValue(0)
        self.crossfade_slider.setToolTip("Crossfade-Dauer in Sekunden (0-5.0)")
        cf_row.addWidget(self.crossfade_slider)
        self.crossfade_label = QLabel("0.0s")
        self.crossfade_label.setFixedWidth(35)
        cf_row.addWidget(self.crossfade_label)
        effects_layout.addLayout(cf_row)

        # Apply Button
        self.btn_apply_effects = QPushButton("Effekte anwenden")
        self.btn_apply_effects.setObjectName("btn_action")
        self.btn_apply_effects.setFixedHeight(32)
        self.btn_apply_effects.setMaximumWidth(300)
        self.btn_apply_effects.setToolTip("Helligkeit/Kontrast/Crossfade auf den gewaehlten Clip anwenden")
        effects_layout.addWidget(self.btn_apply_effects)

        # Preview
        self.effects_preview = QLabel("")
        self.effects_preview.setFixedHeight(180)
        self.effects_preview.setStyleSheet(
            "background: #0a0d12; border: 1px solid rgba(255,255,255,10); border-radius: 4px;"
        )
        self.effects_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        effects_layout.addWidget(self.effects_preview)

        effects_layout.addStretch()
        settings_layout.addWidget(effects_group)

        # Slider-Label Sync (intern)
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_label.setText(str(v))
        )
        self.contrast_slider.valueChanged.connect(
            lambda v: self.contrast_label.setText(str(v))
        )
        self.crossfade_slider.valueChanged.connect(
            lambda v: self.crossfade_label.setText(f"{v / 10:.1f}s")
        )

        settings_layout.addStretch()
        top_splitter.addWidget(settings_panel)

        # Right: Log
        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)

        log_title = QLabel("CONVERT LOG")
        log_title.setStyleSheet("color: #9ca3af; font-weight: 700; font-size: 11px; padding: 2px 4px;")
        log_layout.addWidget(log_title)

        self.convert_log = QTextEdit()
        self.convert_log.setReadOnly(True)
        self.convert_log.setStyleSheet(
            f"background-color: {BG0}; border: 1px solid rgba(255,255,255,15); "
            f"color: {T1}; font-family: 'Consolas';"
        )
        self.convert_log.setToolTip("Protokoll der Video-Konvertierungen")
        self.convert_log.append("[Convert] Bereit. Waehle Ziel-Format und klicke 'Alle Videos standardisieren'.")
        log_layout.addWidget(self.convert_log)

        top_splitter.addWidget(log_panel)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 4)
        top_splitter.setCollapsible(0, True)
        top_splitter.setCollapsible(1, False)

        layout.addWidget(top_splitter)
