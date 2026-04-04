"""EDIT Workspace: Timeline, pacing, anchors, video preview."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QSpinBox, QSplitter,
    QScrollArea, QTreeWidget, QTextEdit,
)
from PySide6.QtCore import Qt, QSize

from ui.timeline import InteractiveTimeline
from ui.clip_inspector import ClipInspectorPanel
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
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,0.05);")
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
        self.btn_preview_play.setAccessibleName("Vorschau Play / Pause")
        self.btn_preview_play.setStatusTip("Video-Vorschau abspielen oder pausieren")
        transport_row.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("\u25A0")
        self.btn_preview_stop.setFixedSize(36, 36)
        self.btn_preview_stop.setIconSize(QSize(24, 24))
        self.btn_preview_stop.setToolTip("Stop")
        self.btn_preview_stop.setAccessibleName("Vorschau Stop")
        self.btn_preview_stop.setStatusTip("Video-Vorschau stoppen und zum Anfang zurueckspringen")
        # NOTE: btn_preview_stop is connected in main.py (PBWindow._wire_signals)
        transport_row.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("00:00 / 00:00")
        self.preview_time_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        self.preview_time_label.setAccessibleName("Vorschau Zeitanzeige")
        transport_row.addWidget(self.preview_time_label)
        transport_row.addStretch()

        self.btn_toggle_inspector = QPushButton("\u25B6")
        self.btn_toggle_inspector.setFixedSize(36, 36)
        self.btn_toggle_inspector.setIconSize(QSize(24, 24))
        self.btn_toggle_inspector.setToolTip("Inspector Panel ein-/ausklappen")
        self.btn_toggle_inspector.setAccessibleName("Inspector Panel ein-/ausklappen")
        self.btn_toggle_inspector.setStatusTip("Inspector-Panel mit Pacing-Einstellungen ein- oder ausklappen")
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
        hdr.setObjectName("subtitle")
        insp.addWidget(hdr)
        self._add_separator(insp)

        # Source selectors
        src_lbl = QLabel("QUELLEN")
        src_lbl.setObjectName("subtitle")
        insp.addWidget(src_lbl)

        self.audio_combo = QComboBox()
        self.audio_combo.setToolTip("Audio-Track fuer BPM-Pacing")
        self.audio_combo.setAccessibleName("Audio-Track Auswahl")
        self.audio_combo.setStatusTip("Audio-Track fuer die BPM-Analyse und das Pacing-Timing waehlen")
        insp.addWidget(self.audio_combo)

        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Video-Clip fuer Vorschau")
        self.video_combo.setAccessibleName("Video-Clip Auswahl")
        self.video_combo.setStatusTip("Video-Clip fuer die Vorschau und den Auto-Edit waehlen")
        insp.addWidget(self.video_combo)

        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("Stimmung / Vibe...")
        self.vibe_input.setToolTip("Freitext: energetisch, melancholisch, aggressiv...")
        self.vibe_input.setAccessibleName("Vibe Eingabe")
        self.vibe_input.setStatusTip("Freitext-Beschreibung der gewuenschten Stimmung fuer den KI-gesteuerten Edit")
        insp.addWidget(self.vibe_input)

        self._add_separator(insp)

        # DJ Pacing Controls
        pacing_lbl = QLabel("DJ PACING")
        pacing_lbl.setObjectName("subtitle")
        insp.addWidget(pacing_lbl)

        # Cut Rate
        cut_rate_row = QHBoxLayout()
        cut_rate_row.setSpacing(4)
        cr_lbl = QLabel("Cut Rate")
        cr_lbl.setFixedWidth(52)
        cr_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        cr_lbl.setToolTip("Basis-Schnittrate: Alle N Beats wird geschnitten")
        cut_rate_row.addWidget(cr_lbl)
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        self.cut_rate_combo.setToolTip("Basis-Schnittrate")
        self.cut_rate_combo.setAccessibleName("Cut Rate")
        self.cut_rate_combo.setStatusTip("Basis-Schnittrate: Alle N Beats wird ein Schnitt gesetzt")
        self.cut_rate_combo.setFixedHeight(22)
        cut_rate_row.addWidget(self.cut_rate_combo, stretch=1)
        insp.addLayout(cut_rate_row)

        # Energy Reactivity
        energy_row = QHBoxLayout()
        energy_row.setSpacing(4)
        er_lbl = QLabel("Reaktivitaet")
        er_lbl.setFixedWidth(52)
        er_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        er_lbl.setToolTip("Energy Reactivity: Erhoehe Cut-Rate bei hohem RMS")
        energy_row.addWidget(er_lbl)
        self.energy_reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.energy_reactivity_slider.setRange(0, 100)
        self.energy_reactivity_slider.setValue(50)
        self.energy_reactivity_slider.setFixedHeight(16)
        self.energy_reactivity_slider.setAccessibleName("Energy Reaktivitaet")
        self.energy_reactivity_slider.setStatusTip("Energy Reactivity: Erhoeht die Schnittrate bei hohem Audio-Pegel (0-100%)")
        self.energy_reactivity_slider.setWhatsThis(
            "Steuert wie stark die Schnittrate auf die Energie des Audio-Signals reagiert. "
            "Hohe Werte: bei lauten Passagen schnellere Schnitte. "
            "Niedrige Werte: gleichmaessige Schnittrate unabhaengig von der Energie."
        )
        energy_row.addWidget(self.energy_reactivity_slider, stretch=1)
        self.energy_reactivity_spin = QSpinBox()
        self.energy_reactivity_spin.setRange(0, 100)
        self.energy_reactivity_spin.setValue(50)
        self.energy_reactivity_spin.setSuffix("%")
        self.energy_reactivity_spin.setFixedWidth(52)
        self.energy_reactivity_spin.setFixedHeight(20)
        self.energy_reactivity_spin.setAccessibleName("Energy Reaktivitaet Wert")
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
        sp_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        sp_lbl.setToolTip("Genre-basiertes Schnitt-Preset")
        style_row.addWidget(sp_lbl)
        self.style_preset_combo = QComboBox()
        self.style_preset_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        self.style_preset_combo.setCurrentIndex(0)
        self.style_preset_combo.setToolTip("Genre-Preset fuer automatische Pacing-Anpassung")
        self.style_preset_combo.setAccessibleName("Style Preset")
        self.style_preset_combo.setStatusTip("Genre-basiertes Schnitt-Preset waehlen (z.B. Techno, House, Cinematic)")
        self.style_preset_combo.setFixedHeight(22)
        style_row.addWidget(self.style_preset_combo, stretch=1)
        insp.addLayout(style_row)

        # Breakdown Behavior
        bd_row = QHBoxLayout()
        bd_row.setSpacing(4)
        bd_lbl = QLabel("Breakdown")
        bd_lbl.setFixedWidth(52)
        bd_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
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
        self.breakdown_combo.setAccessibleName("Breakdown Verhalten")
        self.breakdown_combo.setStatusTip("Verhalten bei niedrigem Audio-Pegel (Breakdowns/Intros) waehlen")
        self.breakdown_combo.setFixedHeight(22)
        bd_row.addWidget(self.breakdown_combo, stretch=1)
        insp.addLayout(bd_row)

        # Legacy slider refs
        self.tempo_slider = self.energy_reactivity_slider
        self.energy_slider = self.energy_reactivity_slider
        self.density_slider = self.energy_reactivity_slider

        self._add_separator(insp)

        # Action buttons
        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(35)
        self.btn_generate.setMaximumWidth(300)
        self.btn_generate.setToolTip("Berechnet Schnittpunkte (BPM + Pacing-Kurve)")
        self.btn_generate.setAccessibleName("Timeline generieren")
        self.btn_generate.setStatusTip("Berechnet Schnittpunkte basierend auf BPM und Pacing-Kurve")
        insp.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(35)
        self.btn_auto_edit.setMaximumWidth(300)
        self.btn_auto_edit.setToolTip("Phase 3: DJ-Pacing + OTIO Timeline + Anker + VectorDB Matching")
        self.btn_auto_edit.setAccessibleName("Auto-Edit starten")
        self.btn_auto_edit.setStatusTip("Vollstaendiger automatischer Edit: DJ-Pacing, OTIO-Timeline, Anker und KI-Clip-Matching")
        insp.addWidget(self.btn_auto_edit)

        self._add_separator(insp)

        # Anchor System
        anchor_lbl = QLabel("ANKER")
        anchor_lbl.setObjectName("subtitle")
        insp.addWidget(anchor_lbl)

        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video/Szene", "Label"])
        self.anchor_list.setMaximumHeight(100)
        self.anchor_list.setToolTip("Audio-Anker: Feste Clip-Positionen fuer den Auto-Edit")
        self.anchor_list.setAccessibleName("Anker Liste")
        self.anchor_list.setWhatsThis(
            "Die Ankerliste zeigt alle fest fixierten Clip-Positionen auf der Timeline. "
            "Anker werden beim Auto-Edit beruecksichtigt und erzwingen bestimmte Clips "
            "zu bestimmten Zeitpunkten in der Musik. "
            "Anker koennen per Rechtsklick auf der Timeline gesetzt werden."
        )
        insp.addWidget(self.anchor_list)

        anchor_btn_row = QHBoxLayout()
        anchor_btn_row.setSpacing(4)
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_add_anchor.setFixedHeight(28)
        self.btn_add_anchor.setMaximumWidth(80)
        self.btn_add_anchor.setToolTip("Neuen Anker hinzufuegen")
        self.btn_add_anchor.setAccessibleName("Anker hinzufuegen")
        self.btn_add_anchor.setStatusTip("Neuen Audio-Anker an der aktuellen Position setzen")
        anchor_btn_row.addWidget(self.btn_add_anchor)

        self.btn_remove_anchor = QPushButton("- Anker")
        self.btn_remove_anchor.setFixedHeight(28)
        self.btn_remove_anchor.setMaximumWidth(80)
        self.btn_remove_anchor.setToolTip("Ausgewaehlten Anker entfernen")
        self.btn_remove_anchor.setAccessibleName("Anker entfernen")
        self.btn_remove_anchor.setStatusTip("Den in der Liste ausgewaehlten Anker loeschen")
        anchor_btn_row.addWidget(self.btn_remove_anchor)

        self.btn_sync_anchors = QPushButton("Sync")
        self.btn_sync_anchors.setFixedHeight(28)
        self.btn_sync_anchors.setMaximumWidth(60)
        self.btn_sync_anchors.setToolTip("Anker synchronisieren")
        self.btn_sync_anchors.setAccessibleName("Anker synchronisieren")
        self.btn_sync_anchors.setStatusTip("Anker-Positionen mit der aktuellen Timeline synchronisieren")
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
        self.btn_learn_ai.setAccessibleName("Als KI-Lernregel speichern")
        self.btn_learn_ai.setStatusTip("Speichert den Anker als KI-Lernregel fuer aehnliche Audio-Situationen")
        insp.addWidget(self.btn_learn_ai)

        # RL Feedback Buttons
        rl_row = QHBoxLayout()
        rl_row.setSpacing(6)
        self.btn_thumbs_up = QPushButton("\U0001f44d")
        self.btn_thumbs_up.setObjectName("btn_secondary")
        self.btn_thumbs_up.setFixedHeight(32)
        self.btn_thumbs_up.setFixedWidth(48)
        self.btn_thumbs_up.setToolTip("Positives Feedback: Gute Edit-Entscheidung")
        self.btn_thumbs_up.setAccessibleName("Positives Feedback")
        self.btn_thumbs_up.setStatusTip("Positives Feedback: Diese Edit-Entscheidung war gut")
        rl_row.addWidget(self.btn_thumbs_up)

        self.btn_thumbs_down = QPushButton("\U0001f44e")
        self.btn_thumbs_down.setObjectName("btn_secondary")
        self.btn_thumbs_down.setFixedHeight(32)
        self.btn_thumbs_down.setFixedWidth(48)
        self.btn_thumbs_down.setToolTip("Negatives Feedback: Schlechte Edit-Entscheidung")
        self.btn_thumbs_down.setAccessibleName("Negatives Feedback")
        self.btn_thumbs_down.setStatusTip("Negatives Feedback: Diese Edit-Entscheidung war schlecht")
        rl_row.addWidget(self.btn_thumbs_down)
        rl_row.addStretch()
        insp.addLayout(rl_row)

        self._add_separator(insp)

        # Keyframe Analysis
        kf_lbl = QLabel("SZENEN-ANALYSE")
        kf_lbl.setObjectName("subtitle")
        insp.addWidget(kf_lbl)

        self.btn_keyframe_string = QPushButton("Keyframe-String generieren")
        self.btn_keyframe_string.setObjectName("btn_ai")
        self.btn_keyframe_string.setFixedHeight(35)
        self.btn_keyframe_string.setMaximumWidth(300)
        self.btn_keyframe_string.setToolTip("Generiert Text-String aller Video-Szenen mit Motion-Werten")
        self.btn_keyframe_string.setAccessibleName("Keyframe-String generieren")
        self.btn_keyframe_string.setStatusTip("Erzeugt einen Text-String mit allen Video-Szenen und Motion-Werten fuer KI-Verarbeitung")
        insp.addWidget(self.btn_keyframe_string)

        self.keyframe_text = QTextEdit()
        self.keyframe_text.setReadOnly(True)
        self.keyframe_text.setMaximumHeight(120)
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
        curve_lbl.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        curve_hdr.addWidget(curve_lbl)
        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(24)
        btn_reset.setFixedWidth(52)
        btn_reset.setToolTip("Pacing-Kurve zuruecksetzen auf 50%")
        btn_reset.setAccessibleName("Pacing-Kurve zuruecksetzen")
        btn_reset.setStatusTip("Setzt die manuelle Pacing-Kurve auf den Ausgangswert (50%) zurueck")
        curve_hdr.addWidget(btn_reset)
        curve_hdr.addStretch()
        bottom_layout.addLayout(curve_hdr)

        self.pacing_curve = PacingCurveWidget()
        self.pacing_curve.setAccessibleName("Manuelle Pacing-Kurve")
        self.pacing_curve.setWhatsThis(
            "Die manuelle Pacing-Kurve erlaubt es, die Schnittgeschwindigkeit ueber die "
            "Zeitachse manuell zu steuern. Ziehe die Kurve nach oben fuer schnellere Schnitte "
            "und nach unten fuer langsamere Schnitte. Diese Kurve ueberlagert das automatische "
            "Energy-Reaktivitaets-Pacing."
        )
        btn_reset.clicked.connect(self.pacing_curve.reset_curve)
        bottom_layout.addWidget(self.pacing_curve)

        # Timeline + Clip Inspector (nebeneinander)
        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(4)
        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip("Timeline: Drag & Drop, Mausrad zum Zoomen, Rubber-Band Selection")
        self.timeline_view.setAccessibleName("Edit Timeline")
        self.timeline_view.setWhatsThis(
            "Die Edit-Timeline zeigt alle Audio- und Video-Clips in zeitlicher Reihenfolge. "
            "Clips koennen per Drag & Drop aus dem Media-Pool eingefuegt werden. "
            "Mausrad: Zoomen. Linke Maustaste: Clips verschieben und Grenzen ziehen. "
            "Rechtsklick auf Clip: Anker setzen. Rubber-Band: Mehrfachauswahl."
        )
        timeline_row.addWidget(self.timeline_view, stretch=1)

        self.clip_inspector = ClipInspectorPanel()
        self.timeline_view.selection_changed.connect(self.clip_inspector.update_from_selection)
        timeline_row.addWidget(self.clip_inspector)

        bottom_layout.addLayout(timeline_row, stretch=1)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #6b7280; font-size: 10px; padding: 1px 4px;")
        bottom_layout.addWidget(self.cut_info_label)

        main_splitter.addWidget(bottom_widget)

        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setSizes([180, 620])
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        layout.addWidget(main_splitter)

        # Tab order: logical navigation through inspector controls
        self.setTabOrder(self.audio_combo, self.video_combo)
        self.setTabOrder(self.video_combo, self.vibe_input)
        self.setTabOrder(self.vibe_input, self.cut_rate_combo)
        self.setTabOrder(self.cut_rate_combo, self.energy_reactivity_slider)
        self.setTabOrder(self.energy_reactivity_slider, self.energy_reactivity_spin)
        self.setTabOrder(self.energy_reactivity_spin, self.style_preset_combo)
        self.setTabOrder(self.style_preset_combo, self.breakdown_combo)
        self.setTabOrder(self.breakdown_combo, self.btn_generate)
        self.setTabOrder(self.btn_generate, self.btn_auto_edit)
        self.setTabOrder(self.btn_auto_edit, self.anchor_list)
        self.setTabOrder(self.anchor_list, self.btn_add_anchor)
        self.setTabOrder(self.btn_add_anchor, self.btn_remove_anchor)
        self.setTabOrder(self.btn_remove_anchor, self.btn_sync_anchors)
        self.setTabOrder(self.btn_sync_anchors, self.btn_learn_ai)
        self.setTabOrder(self.btn_learn_ai, self.btn_thumbs_up)
        self.setTabOrder(self.btn_thumbs_up, self.btn_thumbs_down)
