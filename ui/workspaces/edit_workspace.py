"""EDIT Workspace: Timeline, pacing, anchors, video preview."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QSpinBox, QSplitter,
    QScrollArea, QTreeWidget, QTextEdit,
)
from PySide6.QtCore import Qt, QSize

from ui.timeline import InteractiveTimeline
from ui.widgets.pacing_curve import PacingCurveWidget
from ui.widgets.video_preview import VideoPreviewWidget


class EditWorkspace(QWidget):
    """Edit workspace — video preview, inspector, pacing curve, timeline.

    All buttons/widgets are stored as attributes for PBWindow signal wiring.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    @staticmethod
    def _add_separator(layout):
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1E1E1E; max-height: 1px;")
        layout.addWidget(sep)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: Preview + Inspector
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Video Preview
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(4, 4, 4, 2)
        preview_layout.setSpacing(2)

        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(200, 120)
        preview_layout.addWidget(self.video_preview, stretch=1)

        # Transport bar
        transport_row = QHBoxLayout()
        transport_row.setSpacing(4)
        self.btn_preview_play = QPushButton("\u25B6")
        self.btn_preview_play.setFixedSize(36, 36)
        self.btn_preview_play.setIconSize(QSize(24, 24))
        self.btn_preview_play.setToolTip("Play / Pause")
        transport_row.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("\u25A0")
        self.btn_preview_stop.setFixedSize(36, 36)
        self.btn_preview_stop.setIconSize(QSize(24, 24))
        self.btn_preview_stop.setToolTip("Stop")
        # NOTE: btn_preview_stop is connected in main.py (PBWindow._wire_signals)
        transport_row.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("00:00 / 00:00")
        self.preview_time_label.setStyleSheet("color: #505050; font-size: 10px;")
        transport_row.addWidget(self.preview_time_label)
        transport_row.addStretch()

        self.btn_toggle_inspector = QPushButton("\u25B6")
        self.btn_toggle_inspector.setFixedSize(36, 36)
        self.btn_toggle_inspector.setIconSize(QSize(24, 24))
        self.btn_toggle_inspector.setToolTip("Inspector Panel ein-/ausklappen")
        transport_row.addWidget(self.btn_toggle_inspector)

        preview_layout.addLayout(transport_row)
        top_splitter.addWidget(preview_container)

        # Inspector Panel
        self.inspector_panel = QWidget()
        self.inspector_panel.setObjectName("inspector_panel")
        self.inspector_panel.setMinimumWidth(260)
        self.inspector_panel.setMaximumWidth(400)
        insp_outer = QVBoxLayout(self.inspector_panel)
        insp_outer.setContentsMargins(0, 0, 0, 0)

        insp_scroll = QScrollArea()
        insp_scroll.setWidgetResizable(True)
        insp_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        insp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        insp_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        insp_outer.addWidget(insp_scroll)

        insp_content = QWidget()
        insp = QVBoxLayout(insp_content)
        insp.setContentsMargins(6, 6, 6, 6)
        insp.setSpacing(5)

        hdr = QLabel("INSPECTOR")
        hdr.setStyleSheet("color: #808080; font-weight: 700; font-size: 10px; letter-spacing: 2px;")
        insp.addWidget(hdr)
        self._add_separator(insp)

        # Source selectors
        src_lbl = QLabel("QUELLEN")
        src_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(src_lbl)

        self.audio_combo = QComboBox()
        self.audio_combo.setToolTip("Audio-Track fuer BPM-Pacing")
        insp.addWidget(self.audio_combo)

        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Video-Clip fuer Vorschau")
        insp.addWidget(self.video_combo)

        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("Stimmung / Vibe...")
        self.vibe_input.setToolTip("Freitext: energetisch, melancholisch, aggressiv...")
        insp.addWidget(self.vibe_input)

        self._add_separator(insp)

        # DJ Pacing Controls
        pacing_lbl = QLabel("DJ PACING")
        pacing_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(pacing_lbl)

        # Cut Rate
        cut_rate_row = QHBoxLayout()
        cut_rate_row.setSpacing(4)
        cr_lbl = QLabel("Cut Rate")
        cr_lbl.setFixedWidth(52)
        cr_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        cr_lbl.setToolTip("Basis-Schnittrate: Alle N Beats wird geschnitten")
        cut_rate_row.addWidget(cr_lbl)
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        self.cut_rate_combo.setToolTip("Basis-Schnittrate")
        self.cut_rate_combo.setFixedHeight(22)
        cut_rate_row.addWidget(self.cut_rate_combo, stretch=1)
        insp.addLayout(cut_rate_row)

        # Energy Reactivity
        energy_row = QHBoxLayout()
        energy_row.setSpacing(4)
        er_lbl = QLabel("Reaktivitaet")
        er_lbl.setFixedWidth(52)
        er_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        er_lbl.setToolTip("Energy Reactivity: Erhoehe Cut-Rate bei hohem RMS")
        energy_row.addWidget(er_lbl)
        self.energy_reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.energy_reactivity_slider.setRange(0, 100)
        self.energy_reactivity_slider.setValue(50)
        self.energy_reactivity_slider.setFixedHeight(16)
        energy_row.addWidget(self.energy_reactivity_slider, stretch=1)
        self.energy_reactivity_spin = QSpinBox()
        self.energy_reactivity_spin.setRange(0, 100)
        self.energy_reactivity_spin.setValue(50)
        self.energy_reactivity_spin.setSuffix("%")
        self.energy_reactivity_spin.setFixedWidth(52)
        self.energy_reactivity_spin.setFixedHeight(20)
        self.energy_reactivity_spin.setStyleSheet("font-size: 10px;")
        self.energy_reactivity_slider.valueChanged.connect(self.energy_reactivity_spin.setValue)
        self.energy_reactivity_spin.valueChanged.connect(self.energy_reactivity_slider.setValue)
        energy_row.addWidget(self.energy_reactivity_spin)
        insp.addLayout(energy_row)

        # Style Preset
        style_row = QHBoxLayout()
        style_row.setSpacing(4)
        sp_lbl = QLabel("Style")
        sp_lbl.setFixedWidth(52)
        sp_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        sp_lbl.setToolTip("Genre-basiertes Schnitt-Preset")
        style_row.addWidget(sp_lbl)
        self.style_preset_combo = QComboBox()
        self.style_preset_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        self.style_preset_combo.setCurrentIndex(0)
        self.style_preset_combo.setToolTip("Genre-Preset fuer automatische Pacing-Anpassung")
        self.style_preset_combo.setFixedHeight(22)
        style_row.addWidget(self.style_preset_combo, stretch=1)
        insp.addLayout(style_row)

        # Breakdown Behavior
        bd_row = QHBoxLayout()
        bd_row.setSpacing(4)
        bd_lbl = QLabel("Breakdown")
        bd_lbl.setFixedWidth(52)
        bd_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        bd_lbl.setToolTip("Verhalten bei niedrigem RMS (Breakdowns/Intros)")
        bd_row.addWidget(bd_lbl)
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["Halbieren", "16-Beat erzwingen", "Keine Cuts"])
        self.breakdown_combo.setCurrentIndex(0)
        self.breakdown_combo.setToolTip(
            "Halbieren: Cut-Rate verdoppelt sich\n"
            "16-Beat: Erzwingt 16-Beat Intervalle\n"
            "Keine Cuts: Keine Schnitte bei Breakdowns"
        )
        self.breakdown_combo.setFixedHeight(22)
        bd_row.addWidget(self.breakdown_combo, stretch=1)
        insp.addLayout(bd_row)

        # Legacy slider refs
        self.tempo_slider = self.energy_reactivity_slider
        self.energy_slider = self.energy_reactivity_slider
        self.density_slider = self.energy_reactivity_slider

        self._add_separator(insp)

        # Action buttons
        _gold_btn_style = (
            "QPushButton { background: #d4a44a; color: #0A0A0A; border: none; border-radius: 4px;"
            " font-weight: 600; font-size: 11px; }"
            "QPushButton:hover { background: #e0b45a; }"
            "QPushButton:pressed { background: #b8903e; }"
        )

        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(35)
        self.btn_generate.setMaximumWidth(300)
        self.btn_generate.setToolTip("Berechnet Schnittpunkte (BPM + Pacing-Kurve)")
        self.btn_generate.setStyleSheet(_gold_btn_style)
        insp.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(35)
        self.btn_auto_edit.setMaximumWidth(300)
        self.btn_auto_edit.setToolTip("Phase 3: DJ-Pacing + OTIO Timeline + Anker + LanceDB Matching")
        self.btn_auto_edit.setStyleSheet(_gold_btn_style)
        insp.addWidget(self.btn_auto_edit)

        self._add_separator(insp)

        # Anchor System
        anchor_lbl = QLabel("ANKER")
        anchor_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(anchor_lbl)

        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video/Szene", "Label"])
        self.anchor_list.setMaximumHeight(100)
        self.anchor_list.setStyleSheet(
            "QTreeWidget { background: #0A0A0A; border: 1px solid #1E1E1E; "
            "font-size: 10px; color: #C0C0C0; }"
            "QTreeWidget::item { padding: 1px; }"
        )
        self.anchor_list.setToolTip("Audio-Anker: Feste Clip-Positionen fuer den Auto-Edit")
        insp.addWidget(self.anchor_list)

        anchor_btn_row = QHBoxLayout()
        anchor_btn_row.setSpacing(4)
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_add_anchor.setFixedHeight(28)
        self.btn_add_anchor.setMaximumWidth(80)
        self.btn_add_anchor.setToolTip("Neuen Anker hinzufuegen")
        anchor_btn_row.addWidget(self.btn_add_anchor)

        self.btn_remove_anchor = QPushButton("- Anker")
        self.btn_remove_anchor.setFixedHeight(28)
        self.btn_remove_anchor.setMaximumWidth(80)
        self.btn_remove_anchor.setToolTip("Ausgewaehlten Anker entfernen")
        anchor_btn_row.addWidget(self.btn_remove_anchor)

        self.btn_sync_anchors = QPushButton("Sync")
        self.btn_sync_anchors.setFixedHeight(28)
        self.btn_sync_anchors.setMaximumWidth(60)
        self.btn_sync_anchors.setToolTip("Anker synchronisieren")
        anchor_btn_row.addWidget(self.btn_sync_anchors)
        anchor_btn_row.addStretch()
        insp.addLayout(anchor_btn_row)

        # AI Learning Button
        self.btn_learn_ai = QPushButton("Als KI-Regel lernen")
        self.btn_learn_ai.setObjectName("btn_learn_ai")
        self.btn_learn_ai.setFixedHeight(35)
        self.btn_learn_ai.setMaximumWidth(300)
        self.btn_learn_ai.setToolTip(
            "Speichert den ausgewaehlten Anker als KI-Lernregel.\n"
            "Der Auto-Edit beruecksichtigt diese Entscheidung bei aehnlichem Audio-Kontext."
        )
        insp.addWidget(self.btn_learn_ai)

        # RL Feedback Buttons
        rl_row = QHBoxLayout()
        rl_row.setSpacing(6)
        self.btn_thumbs_up = QPushButton("\U0001f44d")
        self.btn_thumbs_up.setFixedHeight(32)
        self.btn_thumbs_up.setFixedWidth(48)
        self.btn_thumbs_up.setToolTip("Positives Feedback: Gute Edit-Entscheidung")
        self.btn_thumbs_up.setStyleSheet(
            "QPushButton { background: #1a3a1a; border: 1px solid #2a5a2a; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: #2a5a2a; border-color: #3a7a3a; }"
            "QPushButton:pressed { background: #3a7a3a; }"
        )
        rl_row.addWidget(self.btn_thumbs_up)

        self.btn_thumbs_down = QPushButton("\U0001f44e")
        self.btn_thumbs_down.setFixedHeight(32)
        self.btn_thumbs_down.setFixedWidth(48)
        self.btn_thumbs_down.setToolTip("Negatives Feedback: Schlechte Edit-Entscheidung")
        self.btn_thumbs_down.setStyleSheet(
            "QPushButton { background: #3a1a1a; border: 1px solid #5a2a2a; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: #5a2a2a; border-color: #7a3a3a; }"
            "QPushButton:pressed { background: #7a3a3a; }"
        )
        rl_row.addWidget(self.btn_thumbs_down)
        rl_row.addStretch()
        insp.addLayout(rl_row)

        self._add_separator(insp)

        # Keyframe Analysis
        kf_lbl = QLabel("SZENEN-ANALYSE")
        kf_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(kf_lbl)

        self.btn_keyframe_string = QPushButton("Keyframe-String generieren")
        self.btn_keyframe_string.setObjectName("btn_ai")
        self.btn_keyframe_string.setFixedHeight(35)
        self.btn_keyframe_string.setMaximumWidth(300)
        self.btn_keyframe_string.setToolTip("Generiert Text-String aller Video-Szenen mit Motion-Werten")
        insp.addWidget(self.btn_keyframe_string)

        self.keyframe_text = QTextEdit()
        self.keyframe_text.setReadOnly(True)
        self.keyframe_text.setMaximumHeight(120)
        self.keyframe_text.setStyleSheet(
            "QTextEdit { background: #0A0A0A; border: 1px solid #1E1E1E; "
            "font-family: 'Cascadia Code'; font-size: 9px; color: #A0A0A0; }"
        )
        self.keyframe_text.setToolTip("Szenen-Analyse Ergebnis")
        self.keyframe_text.setPlaceholderText("Keyframe-Strings werden hier angezeigt...")
        insp.addWidget(self.keyframe_text)

        insp.addStretch()
        insp_scroll.setWidget(insp_content)

        top_splitter.addWidget(self.inspector_panel)
        top_splitter.setStretchFactor(0, 4)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setCollapsible(0, False)
        top_splitter.setCollapsible(1, True)
        top_splitter.setSizes([900, 300])

        main_splitter.addWidget(top_splitter)

        # Bottom: Pacing Curve + Timeline
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(4, 2, 4, 2)
        bottom_layout.setSpacing(1)

        curve_hdr = QHBoxLayout()
        curve_hdr.setSpacing(4)
        curve_lbl = QLabel("MANUAL PACING")
        curve_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        curve_hdr.addWidget(curve_lbl)
        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(24)
        btn_reset.setFixedWidth(52)
        btn_reset.setToolTip("Pacing-Kurve zuruecksetzen auf 50%")
        curve_hdr.addWidget(btn_reset)
        curve_hdr.addStretch()
        bottom_layout.addLayout(curve_hdr)

        self.pacing_curve = PacingCurveWidget()
        btn_reset.clicked.connect(self.pacing_curve.reset_curve)
        bottom_layout.addWidget(self.pacing_curve)

        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip("Timeline: Drag & Drop, Mausrad zum Zoomen")
        bottom_layout.addWidget(self.timeline_view, stretch=1)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #404040; font-size: 10px; padding: 1px 4px;")
        bottom_layout.addWidget(self.cut_info_label)

        main_splitter.addWidget(bottom_widget)

        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setSizes([180, 620])
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        layout.addWidget(main_splitter)
