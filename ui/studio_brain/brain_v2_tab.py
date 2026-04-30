"""Minimal Studio Brain v2 status tab."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from services.brain_v2.store import BrainStore

logger = logging.getLogger(__name__)


class BrainV2Tab(QWidget):
    """First Brain v2 UI slice: status only, no heavy work on open."""

    def __init__(self, session_factory: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._summary = QLabel("", self)
        self._summary.setWordWrap(True)
        self._ollama = QLabel("", self)
        self._refresh_btn = QPushButton("Refresh", self)
        self._refresh_btn.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._ollama)
        layout.addWidget(self._refresh_btn)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        try:
            stats = BrainStore(self._session_factory).stats()
            self._summary.setText(
                "Brain v2 internal memory\n"
                f"Entities: {stats.get('brain_entity', 0)}\n"
                f"Facts: {stats.get('brain_fact', 0)}\n"
                f"Decisions: {stats.get('brain_decision', 0)}\n"
                f"Memories: {stats.get('brain_memory', 0)}\n"
                f"Notes: {stats.get('brain_note', 0)}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("BrainV2Tab stats unavailable: %s", exc)
            self._summary.setText(
                "Brain v2 internal memory\nNo Brain v2 schema/data available yet."
            )
        self._ollama.setText(f"Ollama: {self._ollama_status()}")

    @staticmethod
    def _ollama_status() -> str:
        try:
            from services.ollama_client import get_ollama_client

            return "available" if get_ollama_client().is_available() else "unavailable"
        except Exception:
            return "unavailable"
