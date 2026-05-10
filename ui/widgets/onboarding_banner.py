"""OnboardingBanner — schmaler Hinweis-Banner pro Workspace (B-296 Phase F).

Dismissable, persistiert pro Banner-ID via QSettings. Konstruktor nimmt
banner_id (eindeutig pro Hinweis), message (User-Text), optional
qsettings_org-Tupel fuer Test-Isolation.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame


class OnboardingBanner(QFrame):
    """B-296: schmaler Hinweis-Banner mit Dismiss-Button + QSettings-Persistenz."""

    dismissed = Signal()

    def __init__(
        self,
        banner_id: str,
        message: str,
        parent: Optional[QWidget] = None,
        qsettings_org: tuple[str, str] = ("PBStudio", "PBStudioApp"),
    ):
        super().__init__(parent)
        self._banner_id = banner_id
        self._qsettings_org = qsettings_org
        self.setObjectName("onboarding_banner")
        self.setStyleSheet(
            "QFrame#onboarding_banner { background: rgba(212,164,74,0.15); "
            "border: 1px solid #d4a44a; border-radius: 3px; }"
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        self.lbl = QLabel(message)
        self.lbl.setStyleSheet("color: #f0c866; font-size: 11px; font-weight: 500;")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl, stretch=1)
        self.btn_dismiss = QPushButton("Verstanden")
        self.btn_dismiss.setFixedHeight(22)
        self.btn_dismiss.setStyleSheet(
            "QPushButton { background: rgba(212,164,74,0.3); border: 1px solid #d4a44a; "
            "color: #f0c866; padding: 2px 10px; font-size: 10px; }"
        )
        self.btn_dismiss.clicked.connect(self._on_dismiss)
        lay.addWidget(self.btn_dismiss)
        self._restore_state()

    def set_message(self, message: str) -> None:
        self.lbl.setText(message)

    def _on_dismiss(self) -> None:
        s = QSettings(*self._qsettings_org)
        s.setValue(f"window/onboarding/{self._banner_id}", True)
        self.hide()
        self.dismissed.emit()

    def _restore_state(self) -> None:
        s = QSettings(*self._qsettings_org)
        if s.value(f"window/onboarding/{self._banner_id}", False, type=bool):
            self.hide()
        else:
            # Explizit setVisible(True) — sonst isHidden() == True bis show()
            # vom Parent kommt. Test test_b296_banner_visible_default verlangt
            # Default-sichtbar direkt nach Konstruktion.
            self.setVisible(True)
