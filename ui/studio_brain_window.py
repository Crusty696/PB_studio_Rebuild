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

T11.1 scope: second tab (index 1, "Gedächtnis") now hosts MemoryTab, backed
by the same BrainService + a BackupService guarding destructive SQL. The
remaining two tabs (Audit, Steer) stay placeholders until T11.2/T11.3.

T11.2 scope: third tab (index 2, "Audit") now hosts AuditTab, backed by the
same BrainService. ``MemoryTab.runSelected`` is wired into
``AuditTab.select_run`` so picking a run in the Gedächtnis tab aligns the
Audit tab's selector (the user still has to switch tabs manually — auto-
switch is a future UX polish).

T11.3 scope: fourth tab (index 3, "Steer") now hosts SteerTab, sharing the
same BrainService + the process-wide ``SteerOverrideQueue``. The Steer tab
is a *producer* of state (runRequested, trackChanged, profileChanged) — no
cross-tab signal receivers are wired in this release.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import shiboken6
from PySide6.QtCore import QSettings, QSize, Signal
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from services.backup_service import BackupService
from services.brain_service import BrainService
from services.steer_override_queue import (
    SteerOverrideQueue,
    get_default_queue,
)
from ui.studio_brain.audit_tab import AuditTab
from ui.studio_brain.memory_tab import MemoryTab
from ui.studio_brain.steer_tab import SteerTab
from ui.studio_brain.structure_tab import StructureTab
# Cycle 11 — Pacing-v2 + D-023 UI-Tabs
from ui.widgets.pacing_decision_explorer import PacingDecisionExplorer
from ui.widgets.graph_cockpit_tab import GraphCockpitTab
from services.graph.cockpit_view_model import CockpitViewModel

logger = logging.getLogger(__name__)


_TAB_LABELS: tuple[str, ...] = (
    "Struktur", "Gedächtnis", "Audit", "Steer",
    # Cycle 11 — Pacing-v2 + D-023 UI-Layer
    "Pacing-Explorer", "Graph-Cockpit",
)
_QSETTINGS_ORG = "PBStudio"
_QSETTINGS_APP = "PBStudioApp"
_KEY_SIZE = "studio_brain/size"
_KEY_LAST_TAB = "studio_brain/last_tab"
_DEFAULT_SIZE = QSize(1100, 720)


def _default_brain_service() -> BrainService:
    """Lazy wrapper around the app's main DB session — used when no explicit
    BrainService is injected. Kept inside a function so test environments that
    never touch the main DB don't pay the `database.session` import cost."""
    from database import nullpool_session  # type: ignore[attr-defined]

    return BrainService(session_factory=nullpool_session)


def _default_backup_service() -> Optional[BackupService]:
    """Return a BackupService wired to the real pb_studio.db + storage/backups.

    Kept optional: headless/test environments that never touch the real DB
    can inject a mock (or ``None``) without paying the filesystem cost.
    ``BackupService.__init__`` calls ``backup_dir.mkdir(parents=True,
    exist_ok=True)`` so the dir is created on-demand.
    """
    try:
        from database.session import APP_ROOT

        from pathlib import Path as _Path

        root = _Path(APP_ROOT)
        return BackupService(
            db_path=root / "pb_studio.db",
            backup_dir=root / "storage" / "backups",
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Default BackupService construction failed: %s", exc)
        return None


class StudioBrainWindow(QMainWindow):
    """Singleton top-level window for the Studio Brain UI."""

    # P12: emitted by the AuditTab's Story-Map dialog when the user clicks
    # a clip card. The payload is the cut's at_timestamp_sec. No internal
    # consumer is wired up yet (the real timeline scrub is a future polish
    # item); the signal exists so downstream code can subscribe without
    # touching this file.
    timelineNavigationRequested = Signal(float)

    _instance: Optional["StudioBrainWindow"] = None

    def __init__(
        self,
        brain_service: Optional[BrainService] = None,
        override_queue: Optional[SteerOverrideQueue] = None,
        backup_service: Optional[BackupService] = None,
    ) -> None:
        super().__init__()
        # Sticky-Tooltips: Tooltips bleiben sichtbar, solange der Cursor auf
        # dem Widget steht (Qt-Default blendet nach 10 s aus). Idempotent.
        from PySide6.QtWidgets import QApplication
        from ui.tooltip_utils import install_sticky_tooltips
        _app = QApplication.instance()
        if _app is not None:
            install_sticky_tooltips(_app)
        self.setWindowTitle("Studio Brain")

        self._brain_service = brain_service if brain_service is not None else _default_brain_service()
        # Process-wide singleton by default; tests may inject a fresh queue.
        # Both the current Structure tab and the future Steer tab (T11.3)
        # read/write this shared instance.
        self._override_queue: SteerOverrideQueue = (
            override_queue if override_queue is not None else get_default_queue()
        )
        # T11.1 — shared BackupService for destructive-action hooks (Memory
        # tab reset, future Steer reset).  Lazy default; tests inject their own.
        self._backup_service: Optional[BackupService] = (
            backup_service if backup_service is not None else _default_backup_service()
        )

        self._tabs = QTabWidget(self)
        # Diagnostik: Per-Tab-Konstruktor-Trace. Hilft beim Lokalisieren
        # von Brain-Open-Hangs (siehe pb_studio.log nach naechstem
        # Restart). Idempotent + billig.
        logger.info("StudioBrainWindow: konstruiere Tabs ...")
        # Index 0 — Struktur (live StructureTab from T10.2a).
        logger.info("StudioBrainWindow: [0/6] StructureTab ...")
        self._structure_tab = StructureTab(
            self._brain_service,
            self._tabs,
            override_queue=self._override_queue,
        )
        self._tabs.addTab(self._structure_tab, _TAB_LABELS[0])
        # Index 1 — Gedächtnis (live MemoryTab from T11.1).
        logger.info("StudioBrainWindow: [1/6] MemoryTab ...")
        self._memory_tab = MemoryTab(
            brain_service=self._brain_service,
            backup_service=self._backup_service,
            parent=self._tabs,
        )
        self._tabs.addTab(self._memory_tab, _TAB_LABELS[1])
        # Index 2 — Audit (live AuditTab from T11.2).
        logger.info("StudioBrainWindow: [2/6] AuditTab ...")
        self._audit_tab = AuditTab(
            brain_service=self._brain_service,
            parent=self._tabs,
        )
        self._tabs.addTab(self._audit_tab, _TAB_LABELS[2])
        # P12 — fan AuditTab's story-map thumbnail-click signal up to the
        # window-level ``timelineNavigationRequested`` so external consumers
        # can listen without poking into the tab. The AuditTab forwards on
        # behalf of any StoryMapDialog it opens.
        self._audit_tab.storyMapThumbnailClicked.connect(
            self._on_story_map_thumbnail_clicked
        )
        # Wire MemoryTab → AuditTab cross-tab signal (T11.2):
        # when the user picks a run in Gedächtnis, align the selector in
        # Audit.  The user still switches tabs manually — auto-switch is a
        # future UX polish.
        self._memory_tab.runSelected.connect(self._audit_tab.select_run)
        # Index 3 — Steer (live SteerTab from T11.3).  Shares the same
        # override_queue as the Structure tab; writes from StructureTab's
        # right-click menu surface here automatically via pendingChanged.
        logger.info("StudioBrainWindow: [3/6] SteerTab ...")
        self._steer_tab = SteerTab(
            brain_service=self._brain_service,
            override_queue=self._override_queue,
            parent=self._tabs,
        )
        self._tabs.addTab(self._steer_tab, _TAB_LABELS[3])

        # Cycle 11 — Index 4: Pacing-Explorer (Decision-Replay + Verdict-Edit)
        # Session-Factory aus dem BrainService recyclen — beide reden gegen
        # dieselbe DB, kein zweites Pool-Setup nötig.
        # Cycle 13 BUG-7: nutze public-property statt _session_factory.
        try:
            session_factory = getattr(self._brain_service, "session_factory", None)
            # Backward-Compat: wenn die public-property noch nicht da ist,
            # lese das (nun als legacy markiert) private Attribut.
            if session_factory is None:
                session_factory = getattr(self._brain_service, "_session_factory", None)
        except Exception:  # broad: alte BrainService-Varianten
            session_factory = None
        logger.info("StudioBrainWindow: [4/6] PacingDecisionExplorer ...")
        self._pacing_explorer_tab = PacingDecisionExplorer(
            session_factory=session_factory,
            parent=self._tabs,
        )
        self._tabs.addTab(self._pacing_explorer_tab, _TAB_LABELS[4])

        # Cycle 11 — Index 5: Graph-Cockpit (D-023 Sigma.js Visualisierung)
        # B-196 Notausgang: ``PB_DISABLE_GRAPH_COCKPIT=1`` haengt einen Stub
        # statt der echten WebEngine-View ein. Hilft, wenn der Tab haengt
        # und der User den Rest des Brain trotzdem nutzen will.
        import os as _os
        if _os.environ.get("PB_DISABLE_GRAPH_COCKPIT") == "1":
            from PySide6.QtWidgets import QLabel
            logger.warning(
                "StudioBrainWindow: [5/6] GraphCockpit DEAKTIVIERT via "
                "PB_DISABLE_GRAPH_COCKPIT=1 — Stub-Tab eingehaengt."
            )
            self._graph_cockpit_tab = QLabel(
                "Graph-Cockpit ist via PB_DISABLE_GRAPH_COCKPIT=1 abgeschaltet.\n"
                "Entferne die Env-Var um den Tab wieder zu aktivieren."
            )
        else:
            logger.info("StudioBrainWindow: [5/6] GraphCockpitTab + CockpitViewModel ...")
            # B-199 F-5: View-Model aus dem BrainService befuellen, sodass
            # der Cockpit-Tab nicht mehr leer rendert. Vorher: ``CockpitViewModel()``
            # ohne Argumente → leerer GraphService → leerer Sigma-Render.
            _cockpit_vm = CockpitViewModel()
            # B-199 F-5: Daten-Quelle merken, damit der Refresh-Button im
            # Cockpit-Tab den Graph nachladen kann.
            _cockpit_vm.set_data_source(self._brain_service)
            try:
                _cockpit_vm.populate_from_brain_service(self._brain_service)
            except Exception as _vm_exc:  # broad: Tab darf nicht haengen
                logger.warning(
                    "B-199 F-5: Cockpit-VM populate fehlgeschlagen "
                    "(Tab oeffnet leer): %s", _vm_exc,
                )
            self._graph_cockpit_tab = GraphCockpitTab(
                view_model=_cockpit_vm,
                parent=self._tabs,
            )
        self._tabs.addTab(self._graph_cockpit_tab, _TAB_LABELS[5])
        logger.info("StudioBrainWindow: alle 6 Tabs konstruiert.")

        # Cross-Tab-Wiring: AuditTab → PacingExplorer (Decision-ID-Forward)
        # Wenn die Audit-Tab eine Decision auswählt, kann der Explorer den
        # gleichen Eintrag im Detail-Panel zeigen.
        try:
            self._audit_tab.cutSelected.connect(
                self._pacing_explorer_tab.select_decision
            )
        except (AttributeError, RuntimeError) as exc:
            logger.debug("AuditTab.cutSelected not wired: %s", exc)

        # Tab-Tooltips (deutsche, einsteigerfreundliche Erklaerungen).
        self._tabs.setTabToolTip(
            0,
            "Uebersicht aller erkannten Szenen. Hier siehst du welche Clips "
            "zu welchem Stil gehoeren, filterst nach Rolle/Stimmung/Stil "
            "und markierst Clips fuer den naechsten Schnitt.",
        )
        self._tabs.setTabToolTip(
            1,
            "Was hat das Studio aus deinen bisherigen Schnitten gelernt? "
            "Zeigt Pacing-Runs, automatisch erkannte Muster und die "
            "dazugehoerigen Entscheidungen. Reset loescht die Lerndaten.",
        )
        self._tabs.setTabToolTip(
            2,
            "Prueft einen einzelnen Pacing-Run im Detail. Fuer jeden "
            "Schnitt: Welcher Clip wurde warum gewaehlt, welche waren die "
            "Alternativen, war es ein Fallback-Schnitt?",
        )
        self._tabs.setTabToolTip(
            3,
            "Steuert den naechsten Pacing-Run. Hier whlst du Audio-Track "
            "und Gewichtsprofil, setzt Pins/Boosts/Excludes und startest "
            "einen neuen Schnitt-Lauf.",
        )
        self._tabs.setTabToolTip(
            4,
            "Pacing-v2 Decision-Replay: pro Schnitt das Reward-Breakdown "
            "(7 Komponenten), die Top-3-Beiträge und die Möglichkeit, "
            "👍/👎 zu vergeben um die Lern-Schleife zu füttern.",
        )
        self._tabs.setTabToolTip(
            5,
            "Graph-Cockpit (D-023): interaktive Visualisierung aller "
            "Audio/Video/Sektion-Knoten + Ähnlichkeitskanten. Klick auf "
            "Knoten zeigt Nachbarn + Edge-Gewichte.",
        )

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
        backup_service: Optional[BackupService] = None,
    ) -> "StudioBrainWindow":
        """Tear down any existing singleton and re-create it with the supplied
        BrainService / override-queue / backup-service. Intended strictly for
        tests — production code should use `instance()`.
        """
        existing = cls._instance
        if existing is not None:
            try:
                existing.close()
                existing.deleteLater()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass
        cls._instance = cls(
            brain_service=brain_service,
            override_queue=override_queue,
            backup_service=backup_service,
        )
        return cls._instance

    # ── Public helpers ─────────────────────────────────────────────────────
    def count_tabs(self) -> int:
        return self._tabs.count()

    # ── P12 internal slots ────────────────────────────────────────────────
    def _on_story_map_thumbnail_clicked(
        self, _scene_id: int, timestamp_sec: float
    ) -> None:
        """Forward Story-Map thumbnail clicks as ``timelineNavigationRequested``.

        The real timeline scrub is wired in a separate task; here we simply
        log + emit so external listeners (or future polish) can subscribe.
        """
        try:
            ts = float(timestamp_sec)
        except (TypeError, ValueError):
            return
        logger.debug(
            "StudioBrainWindow: story-map navigation requested at %.3fs", ts
        )
        self.timelineNavigationRequested.emit(ts)

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

    def closeEvent(self, event: Any) -> None:
        self._save_state()
        super().closeEvent(event)
