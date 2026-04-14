"""EDIT Workspace: Timeline, pacing, anchors, video preview.

P9-Step4: komplettes Redesign mit 4 Sub-Tabs (TIMELINE / PACING /
INSPECTOR / ANKER). Kein Splitter mehr, festes Layout im 1213×836-Frame.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QSpinBox,
    QTreeWidget, QTextEdit, QTabWidget, QFrame,
)
from PySide6.QtCore import Qt, QSize

from ui.timeline import InteractiveTimeline
from ui.clip_inspector import ClipInspectorPanel
from ui.widgets.pacing_curve import PacingCurveWidget
from ui.widgets.video_preview import VideoPreviewWidget


_SUB_TAB_STYLE = """
QTabBar::tab {
    background: transparent;
    color: #6b7280;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 2px 14px;
    min-height: 18px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QTabBar::tab:hover {
    color: #9ca3af;
    background: rgba(255,255,255,0.03);
}
QTabBar::tab:selected {
    color: #f0c866;
    border-bottom: 2px solid #d4a44a;
    background: rgba(212,164,74,0.08);
}
QTabWidget::pane { border: none; }
"""


class EditWorkspace(QWidget):
    """Edit workspace — 4 Sub-Tabs unter dem Hauptlayout-Stack.

    Alle Buttons/Widgets bleiben als ``self.X`` Attribute erhalten, da
    Controllers / PBWindow sie per Name ansprechen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,0.05);")
        return sep

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_SUB_TAB_STYLE)
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_timeline_tab(), "TIMELINE")
        self._tabs.addTab(self._build_pacing_tab(), "PACING")
        self._tabs.addTab(self._build_inspector_tab(), "INSPECTOR")
        self._tabs.addTab(self._build_anker_tab(), "ANKER")
        layout.addWidget(self._tabs)

        # Cross-Tab-Wiring: Timeline-Selection → Inspector-Update
        self.timeline_view.selection_changed.connect(self.clip_inspector.update_from_selection)

        # P9-Step4: alias fuer Rueckwaertskompatibilitaet — alter Code
        # (workspace_setup._toggle_inspector etc.) referenziert "inspector_panel"
        # als das Side-Panel; im Tab-Layout ist das jetzt der INSPECTOR-Tab-Container.
        # Wir geben das ClipInspector-Widget als Stub-Alias zurueck — Toggle-Visibility
        # auf einem Tab-Inhalt ist no-op, aber es crasht nicht.
        self.inspector_panel = self.clip_inspector

        # Tab-Order ueber alle Tabs hinweg (Slider/Combos im PACING-Tab)
        self.setTabOrder(self.audio_combo, self.video_combo)
        self.setTabOrder(self.video_combo, self.vibe_input)
        self.setTabOrder(self.vibe_input, self.cut_rate_combo)
        self.setTabOrder(self.cut_rate_combo, self.energy_reactivity_slider)
        self.setTabOrder(self.energy_reactivity_slider, self.energy_reactivity_spin)
        self.setTabOrder(self.energy_reactivity_spin, self.style_preset_combo)
        self.setTabOrder(self.style_preset_combo, self.breakdown_combo)
        self.setTabOrder(self.breakdown_combo, self.btn_generate)
        self.setTabOrder(self.btn_generate, self.btn_auto_edit)

    # ------------------------------------------------------------------
    # TIMELINE-Tab: Video-Preview + Timeline-View + Cut-Info
    # ------------------------------------------------------------------
    def _build_timeline_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(4)

        # Video-Preview oben (fix 640×360)
        preview_wrap = QWidget()
        ph = QHBoxLayout(preview_wrap)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(4)
        ph.addStretch()
        self.video_preview = VideoPreviewWidget()
        self.video_preview.setFixedSize(640, 360)
        ph.addWidget(self.video_preview)
        ph.addStretch()
        v.addWidget(preview_wrap)

        # Transport (kompakt)
        transport_row = QHBoxLayout()
        transport_row.setSpacing(4)
        transport_row.addStretch()
        self.btn_preview_play = QPushButton("\u25B6")
        self.btn_preview_play.setFixedSize(28, 24)
        self.btn_preview_play.setToolTip("Play / Pause")
        self.btn_preview_play.setAccessibleName("Vorschau Play / Pause")
        transport_row.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("\u25A0")
        self.btn_preview_stop.setFixedSize(28, 24)
        self.btn_preview_stop.setToolTip("Stop")
        self.btn_preview_stop.setAccessibleName("Vorschau Stop")
        transport_row.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("00:00 / 00:00")
        self.preview_time_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        self.preview_time_label.setAccessibleName("Vorschau Zeitanzeige")
        transport_row.addWidget(self.preview_time_label)
        transport_row.addStretch()

        # Inspector-Toggle bleibt erhalten, ist aber im neuen Layout obsolet
        # (Inspector ist eigenes Tab) — wir lassen den Button als hidden Widget
        # damit alte Wirings nicht crashen.
        self.btn_toggle_inspector = QPushButton("\u25B6")
        self.btn_toggle_inspector.setFixedSize(28, 24)
        self.btn_toggle_inspector.setVisible(False)
        self.btn_toggle_inspector.setAccessibleName("Inspector Panel ein-/ausklappen")

        v.addLayout(transport_row)

        # Timeline-View — nimmt Restraum (380px in 836px Tab-Hoehe)
        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip("Timeline: Drag & Drop, Mausrad zum Zoomen, Rubber-Band Selection")
        self.timeline_view.setAccessibleName("Edit Timeline")
        v.addWidget(self.timeline_view, stretch=1)

        # Cut-Info Label (kompakt)
        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #6b7280; font-size: 10px; padding: 1px 4px;")
        v.addWidget(self.cut_info_label)
        return page

    # ------------------------------------------------------------------
    # PACING-Tab: grosse Pacing-Kurve + Combos + Settings + Action-Row
    # ------------------------------------------------------------------
    def _build_pacing_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        # Quellen-Row: Audio + Video + Vibe
        src_row = QHBoxLayout()
        src_row.setSpacing(8)

        a_lbl = QLabel("Audio")
        a_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        src_row.addWidget(a_lbl)
        self.audio_combo = QComboBox()
        self.audio_combo.setToolTip("Audio-Track fuer BPM-Pacing")
        self.audio_combo.setAccessibleName("Audio-Track Auswahl")
        self.audio_combo.setFixedHeight(22)
        src_row.addWidget(self.audio_combo, stretch=2)

        v_lbl = QLabel("Video")
        v_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        src_row.addWidget(v_lbl)
        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Video-Clip fuer Vorschau")
        self.video_combo.setAccessibleName("Video-Clip Auswahl")
        self.video_combo.setFixedHeight(22)
        src_row.addWidget(self.video_combo, stretch=2)

        vi_lbl = QLabel("Vibe")
        vi_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        src_row.addWidget(vi_lbl)
        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("Stimmung / Vibe...")
        self.vibe_input.setAccessibleName("Vibe Eingabe")
        self.vibe_input.setFixedHeight(22)
        src_row.addWidget(self.vibe_input, stretch=3)
        v.addLayout(src_row)

        # Pacing-Kurve gross
        curve_hdr = QHBoxLayout()
        curve_hdr.setSpacing(4)
        curve_lbl = QLabel("MANUAL PACING")
        curve_lbl.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        curve_hdr.addWidget(curve_lbl)
        curve_hdr.addStretch()
        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(22)
        btn_reset.setFixedWidth(56)
        btn_reset.setToolTip("Pacing-Kurve zuruecksetzen auf 50%")
        btn_reset.setAccessibleName("Pacing-Kurve zuruecksetzen")
        curve_hdr.addWidget(btn_reset)
        v.addLayout(curve_hdr)

        self.pacing_curve = PacingCurveWidget()
        self.pacing_curve.setMinimumHeight(280)
        self.pacing_curve.setAccessibleName("Manuelle Pacing-Kurve")
        btn_reset.clicked.connect(self.pacing_curve.reset_curve)
        v.addWidget(self.pacing_curve, stretch=1)

        # Settings-Grid (kompakt 2 Reihen)
        settings_row1 = QHBoxLayout()
        settings_row1.setSpacing(8)
        cr = QLabel("Cut Rate")
        cr.setStyleSheet("color: #6b7280; font-size: 10px;")
        cr.setFixedWidth(68)
        settings_row1.addWidget(cr)
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        self.cut_rate_combo.setAccessibleName("Cut Rate")
        self.cut_rate_combo.setFixedHeight(22)
        settings_row1.addWidget(self.cut_rate_combo, stretch=1)
        sp = QLabel("Style")
        sp.setStyleSheet("color: #6b7280; font-size: 10px;")
        sp.setFixedWidth(40)
        settings_row1.addWidget(sp)
        self.style_preset_combo = QComboBox()
        self.style_preset_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        self.style_preset_combo.setAccessibleName("Style Preset")
        self.style_preset_combo.setFixedHeight(22)
        settings_row1.addWidget(self.style_preset_combo, stretch=1)
        bd = QLabel("Breakdown")
        bd.setStyleSheet("color: #6b7280; font-size: 10px;")
        bd.setFixedWidth(72)
        settings_row1.addWidget(bd)
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["Halbieren", "16-Beat erzwingen", "Keine Cuts"])
        self.breakdown_combo.setAccessibleName("Breakdown Verhalten")
        self.breakdown_combo.setFixedHeight(22)
        settings_row1.addWidget(self.breakdown_combo, stretch=1)
        v.addLayout(settings_row1)

        settings_row2 = QHBoxLayout()
        settings_row2.setSpacing(8)
        er = QLabel("Reaktivitaet")
        er.setStyleSheet("color: #6b7280; font-size: 10px;")
        er.setFixedWidth(68)
        settings_row2.addWidget(er)
        self.energy_reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.energy_reactivity_slider.setRange(0, 100)
        self.energy_reactivity_slider.setValue(50)
        self.energy_reactivity_slider.setFixedHeight(18)
        self.energy_reactivity_slider.setAccessibleName("Energy Reaktivitaet")
        settings_row2.addWidget(self.energy_reactivity_slider, stretch=1)
        self.energy_reactivity_spin = QSpinBox()
        self.energy_reactivity_spin.setRange(0, 100)
        self.energy_reactivity_spin.setValue(50)
        self.energy_reactivity_spin.setSuffix("%")
        self.energy_reactivity_spin.setFixedWidth(56)
        self.energy_reactivity_spin.setFixedHeight(20)
        self.energy_reactivity_spin.setAccessibleName("Energy Reaktivitaet Wert")
        self.energy_reactivity_slider.valueChanged.connect(self.energy_reactivity_spin.setValue)
        self.energy_reactivity_spin.valueChanged.connect(self.energy_reactivity_slider.setValue)
        settings_row2.addWidget(self.energy_reactivity_spin)
        v.addLayout(settings_row2)

        # Action-Row
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(26)
        self.btn_generate.setMaximumWidth(200)
        self.btn_generate.setAccessibleName("Timeline generieren")
        action_row.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(26)
        self.btn_auto_edit.setMaximumWidth(140)
        self.btn_auto_edit.setAccessibleName("Auto-Edit starten")
        action_row.addWidget(self.btn_auto_edit)

        self.btn_thumbs_up = QPushButton("\U0001f44d")
        self.btn_thumbs_up.setObjectName("btn_secondary")
        self.btn_thumbs_up.setFixedHeight(26)
        self.btn_thumbs_up.setFixedWidth(40)
        self.btn_thumbs_up.setToolTip("Positives Feedback")
        self.btn_thumbs_up.setAccessibleName("Positives Feedback")
        action_row.addWidget(self.btn_thumbs_up)

        self.btn_thumbs_down = QPushButton("\U0001f44e")
        self.btn_thumbs_down.setObjectName("btn_secondary")
        self.btn_thumbs_down.setFixedHeight(26)
        self.btn_thumbs_down.setFixedWidth(40)
        self.btn_thumbs_down.setToolTip("Negatives Feedback")
        self.btn_thumbs_down.setAccessibleName("Negatives Feedback")
        action_row.addWidget(self.btn_thumbs_down)
        action_row.addStretch()
        v.addLayout(action_row)
        return page

    # ------------------------------------------------------------------
    # INSPECTOR-Tab: ClipInspector + Keyframe-String-Section
    # ------------------------------------------------------------------
    def _build_inspector_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        # ClipInspector (vorher klein eingeklemmt — jetzt voll im Tab)
        self.clip_inspector = ClipInspectorPanel()
        v.addWidget(self.clip_inspector, stretch=1)

        # Keyframe / Szenen-Analyse
        v.addWidget(self._separator())
        kf_lbl = QLabel("SZENEN-ANALYSE")
        kf_lbl.setObjectName("subtitle")
        kf_lbl.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(kf_lbl)

        self.btn_keyframe_string = QPushButton("Keyframe-String generieren")
        self.btn_keyframe_string.setObjectName("btn_ai")
        self.btn_keyframe_string.setFixedHeight(26)
        self.btn_keyframe_string.setMaximumWidth(240)
        self.btn_keyframe_string.setAccessibleName("Keyframe-String generieren")
        v.addWidget(self.btn_keyframe_string)

        self.keyframe_text = QTextEdit()
        self.keyframe_text.setReadOnly(True)
        self.keyframe_text.setMaximumHeight(180)
        self.keyframe_text.setPlaceholderText("Keyframe-Strings werden hier angezeigt...")
        v.addWidget(self.keyframe_text)
        return page

    # ------------------------------------------------------------------
    # ANKER-Tab: Liste + Hinzufuegen/Entfernen/Sync + KI-Lernregel
    # ------------------------------------------------------------------
    def _build_anker_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        anchor_lbl = QLabel("ANKER (feste Audio-Video-Sync-Punkte)")
        anchor_lbl.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(anchor_lbl)

        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video/Szene", "Label"])
        self.anchor_list.setAccessibleName("Anker Liste")
        v.addWidget(self.anchor_list, stretch=1)

        anchor_btn_row = QHBoxLayout()
        anchor_btn_row.setSpacing(6)
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_add_anchor.setFixedHeight(24)
        self.btn_add_anchor.setMaximumWidth(80)
        self.btn_add_anchor.setAccessibleName("Anker hinzufuegen")
        anchor_btn_row.addWidget(self.btn_add_anchor)

        self.btn_remove_anchor = QPushButton("- Anker")
        self.btn_remove_anchor.setFixedHeight(24)
        self.btn_remove_anchor.setMaximumWidth(80)
        self.btn_remove_anchor.setAccessibleName("Anker entfernen")
        anchor_btn_row.addWidget(self.btn_remove_anchor)

        self.btn_sync_anchors = QPushButton("Sync")
        self.btn_sync_anchors.setFixedHeight(24)
        self.btn_sync_anchors.setMaximumWidth(60)
        self.btn_sync_anchors.setAccessibleName("Anker synchronisieren")
        anchor_btn_row.addWidget(self.btn_sync_anchors)
        anchor_btn_row.addStretch()
        v.addLayout(anchor_btn_row)

        v.addWidget(self._separator())
        self.btn_learn_ai = QPushButton("Als KI-Lernregel speichern")
        self.btn_learn_ai.setObjectName("btn_learn_ai")
        self.btn_learn_ai.setFixedHeight(26)
        self.btn_learn_ai.setMaximumWidth(240)
        self.btn_learn_ai.setAccessibleName("Als KI-Lernregel speichern")
        v.addWidget(self.btn_learn_ai)
        v.addStretch()
        return page
