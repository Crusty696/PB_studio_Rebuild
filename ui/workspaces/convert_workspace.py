"""CONVERT Workspace: Video standardization, batch conversion, clip effects.

P9-Step5: Tab-Layout (BATCH | EFFEKTE) + kompakter LOG-Fuss.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QProgressBar, QTextEdit, QSlider,
    QTabWidget,
)
from PySide6.QtCore import Qt

from ui.theme import BG0, T1
from ui.widgets.workflow_components import SectionTabs, StatusStrip, make_expert_container


class ConvertWorkspace(QWidget):
    """Convert workspace — 2 Sub-Tabs (Batch / Effekte) + LOG-Fuss."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._tabs = SectionTabs()
        self._tabs.setToolTip(
            "Preflight: Videos fuer Analyse, Timeline und Export technisch standardisieren."
        )
        self._tabs.addTab(self._build_batch_tab(), "PREFLIGHT")
        self._tabs.setTabToolTip(0, "Videos im Pool auf ein gemeinsames Ziel-Format konvertieren.")
        layout.addWidget(self._tabs, stretch=1)

        self.preflight_status = StatusStrip("Preflight bereit. Originaldateien bleiben unveraendert.")
        layout.addWidget(self.preflight_status)

        self.expert_tools = make_expert_container(self)
        self.expert_tools.layout().addWidget(self._build_effects_tab())

        # Hidden compatibility log. Raw output belongs to context/expert surfaces,
        # but controllers still append here.
        self.convert_log = QTextEdit()
        self.convert_log.setReadOnly(True)
        self.convert_log.setFixedHeight(110)
        self.convert_log.setVisible(False)
        self.convert_log.setStyleSheet(
            f"background-color: {BG0}; border: 1px solid rgba(255,255,255,15); "
            f"color: {T1}; font-family: 'Consolas'; font-size: 10px;"
        )
        self.convert_log.setToolTip("Protokoll der Video-Konvertierungen")
        self.convert_log.append("[Convert] Bereit. Waehle Ziel-Format und klicke 'Alle Videos standardisieren'.")
        self.expert_tools.layout().addWidget(self.convert_log)

        # Tab-Order
        self.setTabOrder(self.convert_resolution, self.convert_fps)
        self.setTabOrder(self.convert_fps, self.convert_format)
        self.setTabOrder(self.convert_format, self.btn_standardize_all)
        self.setTabOrder(self.btn_standardize_all, self.effects_clip_combo)
        self.setTabOrder(self.effects_clip_combo, self.brightness_slider)
        self.setTabOrder(self.brightness_slider, self.contrast_slider)
        self.setTabOrder(self.contrast_slider, self.crossfade_slider)
        self.setTabOrder(self.crossfade_slider, self.btn_apply_effects)

    # ------------------------------------------------------------------
    def _build_batch_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(8)

        format_group = QGroupBox("Ziel-Format")
        format_layout = QHBoxLayout(format_group)
        format_layout.setSpacing(8)

        format_layout.addWidget(QLabel("Aufloesung:"))
        self.convert_resolution = QComboBox()
        self.convert_resolution.addItems([
            "1920x1080 (1080p)", "2560x1440 (2K)", "3840x2160 (4K)", "1280x720 (720p)"
        ])
        self.convert_resolution.setFixedHeight(22)
        self.convert_resolution.setAccessibleName("Ziel-Aufloesung")
        self.convert_resolution.setToolTip(
            "Ziel-Aufloesung fuer die Standardisierung aller Videos im Pool."
        )
        format_layout.addWidget(self.convert_resolution, stretch=1)

        format_layout.addWidget(QLabel("Framerate:"))
        self.convert_fps = QComboBox()
        self.convert_fps.addItems(["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"])
        self.convert_fps.setFixedHeight(22)
        self.convert_fps.setAccessibleName("Ziel-Framerate")
        self.convert_fps.setToolTip(
            "Ziel-Framerate fuer konvertierte Videos. Einheitliche FPS vermeiden "
            "Ruckler in Timeline und Export."
        )
        format_layout.addWidget(self.convert_fps, stretch=1)

        format_layout.addWidget(QLabel("Container:"))
        self.convert_format = QComboBox()
        self.convert_format.addItems([
            "mp4 (H.264)", "mp4 (H.265/HEVC)", "mov (ProRes)", "mkv (H.264)"
        ])
        self.convert_format.setFixedHeight(22)
        self.convert_format.setAccessibleName("Ziel-Containerformat")
        self.convert_format.setToolTip(
            "Codec/Container fuer standardisierte Clips. H.264 ist kompatibel, "
            "HEVC kleiner, ProRes groesser aber schnittfreundlich."
        )
        format_layout.addWidget(self.convert_format, stretch=1)

        v.addWidget(format_group)

        # Action-Row
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.btn_standardize_all = QPushButton("Alle Videos standardisieren")
        self.btn_standardize_all.setObjectName("btn_accent")
        self.btn_standardize_all.setFixedHeight(28)
        self.btn_standardize_all.setMaximumWidth(260)
        self.btn_standardize_all.setAccessibleName("Alle Videos standardisieren")
        self.btn_standardize_all.setToolTip(
            "Alle Videos im Pool mit den gewaehlten Zielwerten konvertieren. "
            "Die Originaldateien bleiben unveraendert."
        )
        action_row.addWidget(self.btn_standardize_all)

        self.convert_progress = QProgressBar()
        self.convert_progress.setVisible(False)
        self.convert_progress.setTextVisible(True)
        self.convert_progress.setFixedHeight(22)
        self.convert_progress.setFormat("Konvertierung...")
        action_row.addWidget(self.convert_progress, stretch=1)
        v.addLayout(action_row)
        v.addStretch(1)
        return page

    # ------------------------------------------------------------------
    def _build_effects_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(8)

        # Clip-Picker
        pick_row = QHBoxLayout()
        pick_row.setSpacing(6)
        pick_row.addWidget(QLabel("Clip:"))
        self.effects_clip_combo = QComboBox()
        self.effects_clip_combo.setFixedHeight(22)
        self.effects_clip_combo.setAccessibleName("Clip fuer Effekte waehlen")
        self.effects_clip_combo.setToolTip(
            "Clip auswaehlen, fuer den Effektwerte und Vorschau gelten."
        )
        pick_row.addWidget(self.effects_clip_combo, stretch=1)
        v.addLayout(pick_row)

        # Helligkeit
        br_row = QHBoxLayout()
        br_lbl = QLabel("Helligkeit:")
        br_lbl.setFixedWidth(80)
        br_row.addWidget(br_lbl)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setFixedHeight(18)
        self.brightness_slider.setAccessibleName("Helligkeit")
        self.brightness_slider.setToolTip(
            "Helligkeit anpassen: negative Werte dunkler, positive Werte heller."
        )
        br_row.addWidget(self.brightness_slider, stretch=1)
        self.brightness_label = QLabel("0")
        self.brightness_label.setFixedWidth(40)
        self.brightness_label.setAccessibleName("Helligkeit Wert")
        br_row.addWidget(self.brightness_label)
        v.addLayout(br_row)

        # Kontrast
        ct_row = QHBoxLayout()
        ct_lbl = QLabel("Kontrast:")
        ct_lbl.setFixedWidth(80)
        ct_row.addWidget(ct_lbl)
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(0, 300)
        self.contrast_slider.setValue(100)
        self.contrast_slider.setFixedHeight(18)
        self.contrast_slider.setAccessibleName("Kontrast")
        self.contrast_slider.setToolTip(
            "Kontrast anpassen. 100 ist neutral, hoehere Werte wirken knackiger."
        )
        ct_row.addWidget(self.contrast_slider, stretch=1)
        self.contrast_label = QLabel("100")
        self.contrast_label.setFixedWidth(40)
        self.contrast_label.setAccessibleName("Kontrast Wert")
        ct_row.addWidget(self.contrast_label)
        v.addLayout(ct_row)

        # Crossfade
        cf_row = QHBoxLayout()
        cf_lbl = QLabel("Crossfade:")
        cf_lbl.setFixedWidth(80)
        cf_row.addWidget(cf_lbl)
        self.crossfade_slider = QSlider(Qt.Orientation.Horizontal)
        self.crossfade_slider.setRange(0, 50)
        self.crossfade_slider.setValue(0)
        self.crossfade_slider.setFixedHeight(18)
        self.crossfade_slider.setAccessibleName("Crossfade Dauer")
        self.crossfade_slider.setToolTip(
            "Crossfade-Dauer in Zehntelsekunden fuer weichere Uebergaenge."
        )
        cf_row.addWidget(self.crossfade_slider, stretch=1)
        self.crossfade_label = QLabel("0.0s")
        self.crossfade_label.setFixedWidth(40)
        self.crossfade_label.setAccessibleName("Crossfade Wert")
        cf_row.addWidget(self.crossfade_label)
        v.addLayout(cf_row)

        # Apply
        self.btn_apply_effects = QPushButton("Effekte anwenden")
        self.btn_apply_effects.setObjectName("btn_action")
        self.btn_apply_effects.setFixedHeight(26)
        self.btn_apply_effects.setMaximumWidth(220)
        self.btn_apply_effects.setAccessibleName("Effekte anwenden")
        self.btn_apply_effects.setToolTip(
            "Aktuelle Effektwerte auf den ausgewaehlten Clip anwenden."
        )
        v.addWidget(self.btn_apply_effects)

        # Preview
        self.effects_preview = QLabel("")
        self.effects_preview.setMinimumHeight(360)
        self.effects_preview.setStyleSheet(
            "background: #0a0d12; border: 1px solid rgba(255,255,255,10); border-radius: 4px;"
        )
        self.effects_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.effects_preview, stretch=1)

        # Slider-Label-Sync
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_label.setText(str(v))
        )
        self.contrast_slider.valueChanged.connect(
            lambda v: self.contrast_label.setText(str(v))
        )
        self.crossfade_slider.valueChanged.connect(
            lambda v: self.crossfade_label.setText(f"{v / 10:.1f}s")
        )
        return page
