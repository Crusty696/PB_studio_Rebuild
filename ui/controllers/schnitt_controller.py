"""SchnittController — verbindet Workers mit SchnittWorkspace-States.

Plan: docs/superpowers/archive/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md  (Task 9.3)
       Tier-1 Hardening 2026-05-09 — Wiring + State-Konflikt-Schutz.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from services.pacing_profile import PacingProfile
from services.ui_binder import PacingProfileBinder

logger = logging.getLogger(__name__)


class SchnittController(QObject):
    # Tier-1 B7/B8 Signale: weiterleitung an PBWindow-Logik (Folge-Plan)
    request_auto_edit_with_profile = Signal(object)   # PacingProfile
    request_regenerate = Signal(object)               # PacingProfile
    request_open_settings = Signal()
    clip_property_changed = Signal(int, str, float)

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._current_worker: Any | None = None

        # B1: PacingProfile als Single Source of Truth
        self.profile = PacingProfile()
        tab = workspace.editor_view.tab_pacing_anker
        self.binder = PacingProfileBinder(
            self.profile,
            cut_rate_combo=tab.cut_rate_combo,
            style_combo=tab.style_combo,
            reactivity_slider=tab.reactivity_slider,
            reactivity_spin=tab.reactivity_spin,
            breakdown_combo=tab.breakdown_combo,
            vibe_input=tab.vibe_input,
        )
        # Initial-Sync: Widgets reflektieren Profile-Defaults (D3)
        self.binder.apply_profile(self.profile)

        # B6: Cancel-Pfad (Phase 09)
        workspace.cancel_requested.connect(self._on_cancel)
        # B7: Empty-State Preset-Klick
        workspace.preset_selected.connect(self._on_preset_selected)
        # B8: Empty-State Custom-Klick
        workspace.custom_clicked.connect(self._on_custom_clicked)
        # B2: Re-Generate-Button im Pacing-Tab
        tab.btn_regenerate.clicked.connect(self._on_regenerate_clicked)
        # B5: Timeline-Selection -> Inspector-Panel
        tl = workspace.editor_view.tab_schnitt.timeline_view
        inspector = workspace.editor_view.inspector_panel
        if hasattr(tl, "selection_changed") and hasattr(inspector, "update_from_selection"):
            tl.selection_changed.connect(inspector.update_from_selection)
        if hasattr(inspector, "clip_property_changed"):
            inspector.clip_property_changed.connect(self._on_clip_property_changed)

    def attach_worker(self, worker: Any) -> None:
        # B-704/D2: Vorgaenger-Worker sauber abkoppeln. Vorher ueberschrieb
        # attach_worker nur die Referenz — ein noch laufender alter Worker
        # blieb mit _on_done/_on_failed verbunden und sein spaetes done()
        # schaltete den Workspace-State um, waehrend der neue Worker noch
        # rechnete (Loading-Overlay verschwand, Cancel traf den falschen).
        prev = self._current_worker
        if prev is not None and prev is not worker:
            for _sig, _slot in (
                ("progress", self.workspace.show_progress),
                ("done", self._on_done),
                ("failed", self._on_failed),
            ):
                if hasattr(prev, _sig):
                    try:
                        getattr(prev, _sig).disconnect(_slot)
                    except (RuntimeError, TypeError):
                        pass  # bereits getrennt / C++-Objekt weg
            if hasattr(prev, "cancel"):
                try:
                    prev.cancel()
                except Exception:
                    pass
        self._current_worker = worker
        if hasattr(worker, "progress"):
            worker.progress.connect(self.workspace.show_progress)
        if hasattr(worker, "done"):
            worker.done.connect(self._on_done)
        if hasattr(worker, "failed"):
            worker.failed.connect(self._on_failed)

    # ------------------------------------------------------------------
    # D25 — State-Konflikt-Schutz
    # ------------------------------------------------------------------
    def set_active_project_protected(self, project_id: int | None) -> None:
        """Setzt das aktive Projekt nur, wenn der Workspace nicht gerade
        im STATE_LOADING ist. Ein laufender Worker darf nicht durch einen
        Tab-Wechsel implizit ueberschrieben werden.
        """
        from ui.workspaces.schnitt_workspace import STATE_LOADING
        if self.workspace.current_state() == STATE_LOADING:
            return
        self.workspace.set_active_project(project_id)

    def _on_clip_property_changed(self, entry_id: int, field: str, value: float) -> None:
        """Inspector-DB-Write zur sichtbaren Timeline und Host-Logik weitergeben.

        B-523-FIX: Geometrie-relevante Felder (start_time/end_time) aktualisieren
        nur das betroffene Clip-Item in-place statt die ganze Timeline neu zu
        laden. Der frueher genutzte tl.load_from_db() riss die Szene komplett ab
        und liess sie bei async-Reload-Fehlern leer zurueck (Timeline-Ansicht
        A1/V1 verschwand bis App-Neustart). Nicht-geometrische Felder
        (brightness/contrast/crossfade) wirken erst beim Export und brauchen
        keinen Timeline-Refresh.
        """
        tl = self.workspace.editor_view.tab_schnitt.timeline_view
        if field in ("start_time", "end_time") and hasattr(tl, "refresh_clip_geometry_from_db"):
            try:
                tl.refresh_clip_geometry_from_db(entry_id)
            except Exception as exc:
                logger.warning("SchnittController: in-place clip geometry update failed: %s", exc)
        self.clip_property_changed.emit(entry_id, field, value)

    # ------------------------------------------------------------------
    # Worker-Lifecycle
    # ------------------------------------------------------------------
    def _on_done(self, *args, **kwargs):
        # B-704/D1: Stale-Guard — done() eines Workers, der nicht mehr der
        # aktuelle ist (ueberlappende Generierung), darf den Workspace-State
        # nicht umschalten (sonst verschwindet das Loading-Overlay, waehrend
        # der echte Worker noch rechnet).
        sender = self.sender()
        if sender is not None and self._current_worker is not None and sender is not self._current_worker:
            logger.info("SchnittController: ignoriere done() eines veralteten Workers")
            return
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_failed(self, *args, **kwargs):
        # B-704/D1: gleicher Stale-Guard wie _on_done.
        sender = self.sender()
        if sender is not None and self._current_worker is not None and sender is not self._current_worker:
            logger.info("SchnittController: ignoriere failed() eines veralteten Workers")
            return
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_cancel(self):
        if self._current_worker is not None and hasattr(self._current_worker, "cancel"):
            try:
                self._current_worker.cancel()
            except Exception:
                pass
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    # ------------------------------------------------------------------
    # B7 / B8 / B2 Slots
    # ------------------------------------------------------------------
    def _on_preset_selected(self, key: str) -> None:
        if getattr(self.workspace, "_project_id", None) is None:
            self.workspace.set_active_project(None)
            return
        try:
            new_profile = PacingProfile.from_preset(key)
        except ValueError:
            return
        self.binder.apply_profile(new_profile)
        self.workspace.enter_loading()
        self.request_auto_edit_with_profile.emit(self.profile)

    def _on_custom_clicked(self) -> None:
        self.request_open_settings.emit()

    def _on_regenerate_clicked(self) -> None:
        from ui.workspaces.schnitt.regenerate_dialog import confirm_regenerate
        if not confirm_regenerate(self.workspace):
            return
        self.workspace.enter_loading()
        self.request_regenerate.emit(self.profile)
