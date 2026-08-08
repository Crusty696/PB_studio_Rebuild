"""SchnittController — verbindet Workers mit SchnittWorkspace-States.

Plan: docs/superpowers/archive/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md  (Task 9.3)
       Tier-1 Hardening 2026-05-09 — Wiring + State-Konflikt-Schutz.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from services.pacing_profile import PacingProfile
from services.ui_binder import PacingProfileBinder

logger = logging.getLogger(__name__)


def _current_project_token() -> tuple[int, str] | None:
    """B-714: aktive Projekt-Identitaet ("Generation") oder None.

    Vorbild ist der ``expected_db_url``-Guard in
    ``services/video_analysis_service.py`` (dort: ``_current_db_url()`` —
    die Engine-URL ist eindeutig pro Projektordner und wird bei
    ``set_project()`` via ``EngineProxy.swap()`` ausgetauscht). Zusaetzlich
    geht — analog ``services/pacing_beat_grid._engine_cache_identity`` — die
    Identitaet der ECHTEN Engine ein, damit auch ein Swap auf dieselbe URL
    als Projektwechsel zaehlt.

    None bedeutet "nicht ermittelbar" und schaltet den Guard fail-open
    (gleiche Semantik wie ``expected_db_url=None``).
    """
    try:
        from database import session as db_session
        eng = db_session.engine
        try:
            real = object.__getattribute__(eng, "_engine")
        except AttributeError:
            real = eng
        return (id(real), str(getattr(eng, "url", "")))
    except Exception as exc:  # broad catch: Token-Ermittlung darf nie crashen
        logger.debug("SchnittController: Projekt-Token nicht ermittelbar: %s", exc)
        return None


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
        # B-714: Projekt-Token beim Worker-Start (siehe attach_worker).
        self._worker_project_token: tuple[int, str] | None = None
        # B-717: Echo-Fenster gegen Doppel-Push im selben Event-Turn.
        # Liste statt QObject-Attribut, damit der Timer-Callback keine
        # Referenz auf dieses QObject halten muss (kein Zugriff auf ein
        # evtl. bereits geloeschtes C++-Objekt).
        self._push_echo: list[bool] = [False]
        self._last_push_key: tuple[Any, Any] | None = None

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
                # B-766: Der Supersede-Cancel war komplett still — ein neuer
                # Auto-Edit-Klick ersetzte den laufenden Lauf ohne Log-Zeile
                # oder UI-Hinweis. Genau das liess am 2026-08-06 einen
                # 4,5-Minuten-Lauf scheinbar grundlos bei Segment 0 sterben.
                logger.warning(
                    "B-766: Laufender Worker %s wird durch neuen Lauf "
                    "ersetzt (Supersede-Cancel).",
                    type(prev).__name__,
                )
                try:
                    prev.cancel()
                except Exception:
                    pass
        self._current_worker = worker
        # B-714: Projekt-Identitaet zum Start festhalten. _on_done/_on_failed
        # duerfen ein Ergebnis nur anwenden, wenn noch dasselbe Projekt aktiv
        # ist (Vorbild: expected_db_url in store_scenes_in_db).
        self._worker_project_token = _current_project_token()
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
        # B-717: Der Cockpit-Sprung nach SCHNITT pusht doppelt —
        # ``nav_bar.set_workspace(2)`` loest ueber _on_workspace_changed
        # bereits _push_active_project_to_schnitt aus, danach ruft
        # _handle_cockpit_action es nochmal direkt auf. Jeder Push kostet
        # eine synchrone TimelineEntry-COUNT-Query
        # (SchnittWorkspace.refresh_state_from_db) im GUI-Thread. Ein
        # identischer Push im selben Event-Turn ist eine Wiederholung ohne
        # neue Information und wird verworfen; nach dem naechsten
        # Event-Loop-Turn ist wieder alles erlaubt (keine dauerhafte
        # Dedup -> kein Stale-State-Risiko).
        key = (_current_project_token(), project_id)
        if self._push_echo[0] and key == self._last_push_key:
            logger.debug(
                "SchnittController: doppelter Projekt-Push (%s) im selben "
                "Event-Turn verworfen (B-717)", project_id,
            )
            return
        self._last_push_key = key
        echo = self._push_echo
        echo[0] = True
        QTimer.singleShot(0, lambda: echo.__setitem__(0, False))
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
    def _worker_project_changed(self) -> bool:
        """B-714: Laeuft das Ergebnis in ein anderes Projekt als beim Start?"""
        started = self._worker_project_token
        if started is None:
            return False
        now = _current_project_token()
        if now is None:
            return False
        return now != started

    def _discard_foreign_project_result(self, kind: str) -> None:
        """B-714: Ergebnis eines Workers aus einem anderen Projekt verwerfen.

        Ohne Guard lief ``refresh_state_from_db()`` mit der ALTEN
        ``workspace._project_id`` gegen die NEUE Projekt-DB (der Tab-Wechsel
        konnte den Wechsel nicht durchreichen, weil
        ``set_active_project_protected`` waehrend STATE_LOADING blockt) —
        das Ergebnis landete im falschen Projekt.

        Der Workspace wird auf das jetzt aktive Projekt zurueckgesetzt, sonst
        bliebe er dauerhaft im LOADING-State haengen (jeder heilende Push
        wird dort ja gerade blockiert).
        """
        logger.error(
            "SchnittController: Projekt-Mismatch — %s() gehoert zu Projekt %s, "
            "aktiv ist %s. Ergebnis wird NICHT auf den SCHNITT-Workspace "
            "angewandt (B-714).",
            kind, self._worker_project_token, _current_project_token(),
        )
        self._current_worker = None
        self._worker_project_token = None
        pid = None
        try:
            from database import get_active_project_id
            pid = get_active_project_id()
        except Exception as exc:  # broad catch: Resync darf nie crashen
            logger.warning("SchnittController: aktive project_id unbekannt: %s", exc)
        try:
            self.workspace.set_active_project(pid)
        except Exception as exc:  # broad catch: Resync darf nie crashen
            logger.warning("SchnittController: Projekt-Resync fehlgeschlagen: %s", exc)

    def _on_done(self, *args, **kwargs):
        # B-704/D1: Stale-Guard — done() eines Workers, der nicht mehr der
        # aktuelle ist (ueberlappende Generierung), darf den Workspace-State
        # nicht umschalten (sonst verschwindet das Loading-Overlay, waehrend
        # der echte Worker noch rechnet).
        sender = self.sender()
        if sender is not None and self._current_worker is not None and sender is not self._current_worker:
            logger.info("SchnittController: ignoriere done() eines veralteten Workers")
            return
        # B-714: Projekt-Generations-Guard VOR dem Anwenden.
        if self._worker_project_changed():
            self._discard_foreign_project_result("done")
            return
        self.workspace.refresh_state_from_db()
        self._current_worker = None
        self._worker_project_token = None

    def _on_failed(self, *args, **kwargs):
        # B-704/D1: gleicher Stale-Guard wie _on_done.
        sender = self.sender()
        if sender is not None and self._current_worker is not None and sender is not self._current_worker:
            logger.info("SchnittController: ignoriere failed() eines veralteten Workers")
            return
        # B-714: gleicher Projekt-Generations-Guard wie in _on_done.
        if self._worker_project_changed():
            self._discard_foreign_project_result("failed")
            return
        self.workspace.refresh_state_from_db()
        self._current_worker = None
        self._worker_project_token = None

    def _on_cancel(self):
        # B-772: Der Overlay-Button "Auto-Edit abbrechen" cancelte nur
        # self._current_worker. Der konnte durch den zweiten Worker-Pfad
        # (attach_worker(self._cuts_worker)) ersetzt oder bereits None sein
        # — der Klick schloss dann nur das Overlay, der Auto-Edit-TASK lief
        # weiter (Livetest 2026-08-07, Playbook 2.7). Fix: zusaetzlich den
        # TaskEngine-Task kooperativ abbrechen — derselbe Pfad wie der
        # TASKS-Panel-Abbrechen, der live nachweislich wirkt.
        worker = self._current_worker
        if worker is not None and hasattr(worker, "cancel"):
            try:
                worker.cancel()
            except Exception:
                pass
        task_id = getattr(worker, "task_id", None)
        if task_id:
            try:
                from services.task_manager import GlobalTaskManager
                GlobalTaskManager.instance().cancel_task(task_id)
            except Exception as exc:
                logger.warning(
                    "B-772: TaskEngine-Cancel fuer %s fehlgeschlagen: %s",
                    task_id, exc,
                )
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
