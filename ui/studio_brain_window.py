"""StudioBrainWindow — top-level QMainWindow shell for the Studio Brain UI.

Design §3 (Structure / Memory / Agent): the Studio Brain is the user-facing
read-out of the learning loop. It hosts four tabs:

    Struktur  — compatibility graph, style buckets (T10.2/T11.x)
    Gedächtnis — learned patterns, feedback stats (T11.x)
    Audit     — decision replay, pacing runs (T11.x)
    Steer     — hand-tuning sliders and resets (T11.x)

T10.1 scope: window shell + four empty placeholder QWidgets inside a
QTabWidget. The window is a process-wide singleton (`.instance()`), and the
last size + last selected tab are persisted via QSettings under the
("PBStudio", "PBStudioApp") namespace.

T10.2a scope: first tab (index 0, "Struktur") now hosts StructureTab,
backed by a BrainService. The remaining three tabs stay placeholders until
their own dispatches land.
"""

from __future__ import annotations

import logging
from typing import Optional

import shiboken6
from PySide6.QtCore import QSettings, QSize
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from services.brain_service import BrainService
from services.steer_override_queue import (
    SteerOverrideQueue,
    get_default_queue,
)
from ui.studio_brain.structure_tab import StructureTab

logger = logging.getLogger(__name__)


_TAB_LABELS: tuple[str, ...] = ("Struktur", "Gedächtnis", "Audit", "Steer")
_QSETTINGS_ORG = "PBStudio"
_QSETTINGS_APP = "PBStudioApp"
_KEY_SIZE = "studio_brain/size"
_KEY_LAST_TAB = "studio_brain/last_tab"
_DEFAULT_SIZE = QSize(1100, 720)


def _default_brain_service() -> BrainService:
    """Lazy wrapper around the app's main DB session — used when no explicit
    BrainService is injected. Kept inside a function so test environments that
    never touch the main DB don't pay the `database.session` import cost."""
    from database import nullpool_session

    return BrainService(session_factory=nullpool_session)


class StudioBrainWindow(QMainWindow):
    """Singleton top-level window for the Studio Brain UI."""

    _instance: Optional["StudioBrainWindow"] = None

    def __init__(
        self,
        brain_service: Optional[BrainService] = None,
        override_queue: Optional[SteerOverrideQueue] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Studio Brain")

        self._brain_service = brain_service if brain_service is not None else _default_brain_service()
        # Process-wide singleton by default; tests may inject a fresh queue.
        # Both the current Structure tab and the future Steer tab (T11.3)
        # read/write this shared instance.
        self._override_queue: SteerOverrideQueue = (
            override_queue if override_queue is not None else get_default_queue()
        )

        self._tabs = QTabWidget(self)
        # Index 0 — Struktur (live StructureTab from T10.2a).
        self._structure_tab = StructureTab(
            self._brain_service,
            self._tabs,
            override_queue=self._override_queue,
        )
        self._tabs.addTab(self._structure_tab, _TAB_LABELS[0])
        # Indices 1..3 — still placeholders (filled by T11.x dispatches).
        for label in _TAB_LABELS[1:]:
            placeholder = QWidget(self._tabs)
            self._tabs.addTab(placeholder, label)
        self.setCentralWidget(self._tabs)

        self._restore_state()

    # ── Singleton ──────────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "StudioBrainWindow":
        """Return the shared StudioBrainWindow, creating it lazily.

        Also recreates the instance if the underlying C++ QMainWindow has
        been deleted (e.g. after `close()` + `deleteLater()` reaped the
        object). Without this check, `cls._instance` would be a dangling
        Python reference and attribute access would raise
        ``RuntimeError: Internal C++ object ... already deleted.``
        """
        if cls._instance is None or not shiboken6.isValid(cls._instance):
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_test(
        cls,
        brain_service: Optional[BrainService] = None,
        override_queue: Optional[SteerOverrideQueue] = None,
    ) -> "StudioBrainWindow":
        """Tear down any existing singleton and re-create it with the supplied
        BrainService / override-queue. Intended strictly for tests —
        production code should use `instance()`.
        """
        existing = cls._instance
        if existing is not None:
            try:
                existing.close()
                existing.deleteLater()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass
        cls._instance = cls(
            brain_service=brain_service, override_queue=override_queue
        )
        return cls._instance

    # ── Public helpers ─────────────────────────────────────────────────────
    def count_tabs(self) -> int:
        return self._tabs.count()

    # ── QSettings persistence ──────────────────────────────────────────────
    def _restore_state(self) -> None:
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        size = settings.value(_KEY_SIZE)
        if isinstance(size, QSize) and size.isValid():
            self.resize(size)
        else:
            self.resize(_DEFAULT_SIZE)

        last_tab = settings.value(_KEY_LAST_TAB)
        if last_tab is not None:
            try:
                idx = int(last_tab)
            except (ValueError, TypeError):
                idx = 0
            if 0 <= idx < self._tabs.count():
                self._tabs.setCurrentIndex(idx)

    def _save_state(self) -> None:
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        try:
            settings.setValue(_KEY_SIZE, self.size())
        except Exception as exc:  # best-effort — never crash on close
            logger.debug("studio_brain save size: %s", exc)
        try:
            settings.setValue(_KEY_LAST_TAB, self._tabs.currentIndex())
        except Exception as exc:
            logger.debug("studio_brain save last_tab: %s", exc)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_state()
        super().closeEvent(event)
