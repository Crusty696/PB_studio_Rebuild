"""Empty-State der SCHNITT-Workspace: Quick-Lane mit Preset-Buttons."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)


_PRESETS = [
    ("Techno",    "Schnell, druckvoll. 4 Beats, Reaktivität 70 %."),
    ("Cinematic", "Ruhig, langsam. 16 Beats, Reaktivität 30 %."),
    ("House",     "Mittel groovig. 8 Beats, Reaktivität 50 %."),
    ("Festival",  "Maximaler Druck. 1 Beat, Reaktivität 90 %."),
]


class SchnittEmptyView(QWidget):
    preset_selected = Signal(str)
    custom_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_empty")
        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(16)
        layout.addStretch(1)

        self.title = QLabel("Noch keine Timeline vorhanden.")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-size: 22px; font-weight: 800; color: #f9fafb;")
        layout.addWidget(self.title)

        self.subtitle = QLabel("Wähle einen Auto-Edit Stil, um zu starten.")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet("color: #9ca3af; font-size: 13px;")
        layout.addWidget(self.subtitle)

        layout.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(12)
        for key, hint in _PRESETS:
            btn = self._make_preset_button(key, hint)
            self._buttons[key] = btn
            row.addWidget(btn)
        layout.addLayout(row)

        self.btn_custom = QPushButton("Eigene Einstellungen…")
        self.btn_custom.setFixedHeight(28)
        self.btn_custom.setToolTip(
            "SCHNITT mit eigenen Pacing- und Auto-Edit-Einstellungen starten."
        )
        self.btn_custom.setAccessibleName("Eigene SCHNITT-Einstellungen oeffnen")
        self.btn_custom.clicked.connect(self.custom_clicked)
        custom_row = QHBoxLayout()
        custom_row.addStretch(1)
        custom_row.addWidget(self.btn_custom)
        custom_row.addStretch(1)
        layout.addLayout(custom_row)

        layout.addStretch(2)

    def _make_preset_button(self, key: str, hint: str) -> QPushButton:
        btn = QPushButton(f"{key}\n\n{hint}")
        btn.setObjectName("preset_button")
        btn.setToolTip(f"Auto-Edit-Preset {key} starten: {hint}")
        btn.setAccessibleName(f"Auto-Edit Preset {key}")
        btn.setMinimumSize(180, 110)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setStyleSheet(
            "QPushButton#preset_button {"
            "  background:#0f1318; border:1px solid rgba(255,255,255,30);"
            "  border-radius:8px; color:#e8e6e3; font-size:13px; padding:12px;"
            "}"
            "QPushButton#preset_button:hover {"
            "  border:1px solid #d4a44a; background:#181f27;"
            "}"
        )
        btn.clicked.connect(lambda _checked, k=key: self.preset_selected.emit(k))
        return btn

    def preset_keys(self) -> list[str]:
        return [k for k, _ in _PRESETS]

    def set_project_available(self, available: bool) -> None:
        if available:
            self.title.setText("Noch keine Timeline vorhanden.")
            self.subtitle.setText("Wähle einen Auto-Edit Stil, um zu starten.")
            custom_tip = "SCHNITT mit eigenen Pacing- und Auto-Edit-Einstellungen starten."
        else:
            self.title.setText("Kein Projekt aktiv.")
            self.subtitle.setText("Öffne zuerst ein Projekt, bevor Auto-Edit gestartet werden kann.")
            custom_tip = "Erst ein Projekt oeffnen, dann eigene SCHNITT-Einstellungen starten."

        for key, btn in self._buttons.items():
            btn.setEnabled(available)
            if available:
                hint = dict(_PRESETS).get(key, "")
                btn.setToolTip(f"Auto-Edit-Preset {key} starten: {hint}")
            else:
                btn.setToolTip(f"Auto-Edit-Preset {key} ist erst mit aktivem Projekt verfuegbar.")
        self.btn_custom.setEnabled(available)
        self.btn_custom.setToolTip(custom_tip)
