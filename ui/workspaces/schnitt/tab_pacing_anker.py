"""Sub-Tab 'Pacing & Anker' im SCHNITT-Editor (Phase 06 / Task 6.1)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSplitter,
    QComboBox, QSlider, QSpinBox, QLineEdit, QPushButton, QTreeWidget,
)
from ui.widgets.pacing_curve import PacingCurveWidget


class SchnittTabPacingAnker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_pacing_column())
        splitter.addWidget(self._build_anker_column())
        splitter.setSizes([500, 500])
        outer.addWidget(splitter)

    def _build_pacing_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("MANUAL PACING"))
        self.pacing_curve = PacingCurveWidget()
        self.pacing_curve.setMinimumHeight(280)
        v.addWidget(self.pacing_curve, stretch=1)

        # Settings-Grid
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._small_label("Cut Rate"))
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        row1.addWidget(self.cut_rate_combo, stretch=1)
        row1.addWidget(self._small_label("Style"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        row1.addWidget(self.style_combo, stretch=1)
        row1.addWidget(self._small_label("Breakdown"))
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["halve", "force16", "none"])
        row1.addWidget(self.breakdown_combo, stretch=1)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._small_label("Reaktivität"))
        self.reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.reactivity_slider.setRange(0, 100)
        self.reactivity_slider.setValue(50)
        row2.addWidget(self.reactivity_slider, stretch=1)
        self.reactivity_spin = QSpinBox()
        self.reactivity_spin.setRange(0, 100)
        self.reactivity_spin.setSuffix("%")
        self.reactivity_spin.setValue(50)
        row2.addWidget(self.reactivity_spin)
        v.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._small_label("Vibe"))
        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("z.B. 'dunkel, strobo, club'")
        row3.addWidget(self.vibe_input, stretch=1)
        v.addLayout(row3)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.btn_regenerate = QPushButton("Mit neuen Pacing-Einstellungen generieren")
        self.btn_regenerate.setObjectName("btn_accent")
        self.btn_regenerate.setFixedHeight(30)
        self.btn_regenerate.setStyleSheet(
            "QPushButton#btn_accent {"
            " background:#d4a44a; color:#0a0d12; font-weight:700;"
            " border:none; border-radius:4px; padding:0 14px;"
            "}"
            "QPushButton#btn_accent:hover { background:#f0c866; }"
        )
        action_row.addWidget(self.btn_regenerate)
        v.addLayout(action_row)

        return col

    def _build_anker_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("ANKER (feste Audio-Video-Sync-Punkte)"))
        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video", "Label", "Gewicht"])
        self.anchor_list.setSortingEnabled(True)
        v.addWidget(self.anchor_list, stretch=1)

        toolbar = QHBoxLayout()
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_remove_anchor = QPushButton("− Anker")
        self.btn_sync_anchors = QPushButton("Sync")
        for b in (self.btn_add_anchor, self.btn_remove_anchor, self.btn_sync_anchors):
            b.setFixedHeight(24)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        v.addLayout(toolbar)

        self.btn_learn_ai = QPushButton("Als KI-Lernregel speichern")
        self.btn_learn_ai.setFixedHeight(24)
        v.addWidget(self.btn_learn_ai)

        return col

    @staticmethod
    def _small_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#6b7280; font-size:9px; font-weight:700; letter-spacing:1px;")
        return lbl
