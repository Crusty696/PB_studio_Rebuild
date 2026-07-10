"""Shared workflow UI primitives for the Director's Cockpit.

Small, boring widgets on purpose: the rebuild uses stable task surfaces,
not decorative effects or per-page bespoke styling.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.theme import SECTION_TAB_STYLE


class WorkflowHeader(QWidget):
    """Compact page header with title, short scope, and optional right slot."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 4)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("title")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        text_col.addWidget(self.title)
        if subtitle:
            text_col.addWidget(self.subtitle)
        layout.addLayout(text_col, stretch=1)

        self.action_slot = QHBoxLayout()
        self.action_slot.setSpacing(6)
        layout.addLayout(self.action_slot)


class PrimaryActionBar(QWidget):
    """One visible primary command plus optional secondary controls."""

    def __init__(self, primary_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        self.primary_button = QPushButton(primary_text)
        self.primary_button.setObjectName("btn_accent")
        self.primary_button.setFixedHeight(28)
        layout.addWidget(self.primary_button)
        self.secondary_slot = QHBoxLayout()
        self.secondary_slot.setSpacing(6)
        layout.addLayout(self.secondary_slot)
        layout.addStretch(1)


class StatusStrip(QWidget):
    """Neutral status row for prerequisites and live state."""

    def __init__(self, text: str = "Bereit", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("status_strip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)
        self.label = QLabel(text)
        self.label.setStyleSheet("color:#9ca3af; font-size:10px;")
        layout.addWidget(self.label, stretch=1)

    def set_status(self, text: str) -> None:
        self.label.setText(text)


class SectionTabs(QTabWidget):
    """Shared low-noise tab styling for secondary sections."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setStyleSheet(SECTION_TAB_STYLE)


class ContextPanel(SectionTabs):
    """Right-side context panel. Collapsed by default, contents survive."""

    DEFAULT_WIDTH = 300  # Start-/Wunschbreite (nicht mehr starr, siehe unten)
    MIN_WIDTH = 220      # 2026-07-10: darunter werden Tabs/Buttons abgeschnitten

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("right_panel")
        self.setTabPosition(QTabWidget.TabPosition.North)
        self.set_context_visible(False)

    def set_context_visible(self, visible: bool) -> None:
        # 2026-07-10 (User): Das Dock ist an-/abdockbar -> es darf NICHT starr sein.
        # Statt setFixedWidth nur eine Mindestbreite + freies Maximum, damit der
        # User die Breite per Dock-Splitter frei ziehen kann. Beim Ausblenden
        # kollabiert es auf 0.
        if visible:
            self.setMinimumWidth(self.MIN_WIDTH)
            self.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX -> frei resizable
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(0)
        self.setVisible(visible)


def make_expert_container(parent: QWidget | None = None) -> QFrame:
    """Hidden parent for compatibility widgets removed from main flow."""
    frame = QFrame(parent)
    frame.setObjectName("expert_tools")
    frame.setVisible(False)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    frame.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    return frame
