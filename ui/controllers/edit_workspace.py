"""EditWorkspaceController — Refactored from EditWorkspaceMixin."""

import logging
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QDoubleSpinBox,
    QComboBox, QPushButton, QDialog, QTreeWidgetItem,
)
from PySide6.QtCore import Qt, QTimer
from database import engine, AudioTrack, VideoClip, Scene, get_active_project_id
from sqlalchemy import text, select
from sqlalchemy.orm import Session as DBSession
from services.task_manager import GlobalTaskManager, TaskManagerProxy
from services.pacing_service import (
    PacingSettings, calculate_cut_points, CutPoint,
    AdvancedPacingSettings, generate_keyframe_strings_for_project,
)
from services.timeline_service import TimelineService
from workers import AutoEditWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()

class EditWorkspaceController(PBComponent):
    """Edit workspace methods for PBWindow."""

    def _on_video_combo_changed(self, index: int):
        video_id = self.window.video_combo.currentData()
        if video_id is None:
            self.window.video_preview.setText("Keine Vorschau")
            return
        with DBSession(engine) as session:
            # B-625: column-select statt session.get(VideoClip) — laed keine
            # selectin-scenes (keyframe_paths/embedding_indices-Blobs) mit.
            clip = session.execute(
                select(VideoClip.file_path, VideoClip.duration).where(
                    VideoClip.id == video_id
                )
            ).first()
            if clip and clip.file_path:
                dur = clip.duration if clip.duration else 0.0
                self.window.video_preview.load_video(clip.file_path, dur)

    def _toggle_preview_play(self):
        self.window.video_preview.toggle_play()

    def _on_preview_position_changed(self, current: float, total: float):
        """Update the time label in the transport bar on every frame advance."""
        def _fmt(sec: float) -> str:
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"
        self.window.preview_time_label.setText(f"{_fmt(current)} / {_fmt(total)}")

    def _on_preview_state_changed(self, is_playing: bool):
        """Flip play button icon to reflect current playback state."""
        self.window.btn_preview_play.setText("\u23F8" if is_playing else "\u25B6")

    def _on_audio_combo_changed(self, index: int):
        """Audio-Track gewechselt: Pacing-Kurven-Dauer aktualisieren."""
        audio_id = self.window.audio_combo.currentData()
        if hasattr(self.window, "_schnitt_coordinator"):
            self.window._schnitt_coordinator.refresh_audio(audio_id)
        if audio_id is None:
            if hasattr(self.window, "_schnitt_audio_binder"):
                self.window._schnitt_audio_binder.update_stems(None, None)
                self.window._schnitt_audio_binder.set_duration(0.0)
            return
        if hasattr(self.window, "stems"):
            self.window.stems._update_stem_workspace(audio_id)
        with DBSession(engine) as session:
            # B-625: column-select statt session.get(AudioTrack) — vermeidet
            # eager beatgrid/waveform_data-Blobs (lazy='joined'), die den
            # Qt-Main-Thread einfrieren.
            track = session.execute(
                select(AudioTrack.duration, AudioTrack.title).where(
                    AudioTrack.id == audio_id
                )
            ).first()
            if track and track.duration:
                self.window.pacing_curve.set_duration(track.duration)
                if hasattr(self.window, "console_text"):
                    self.window.console_text.append(
                        f"[Edit] Audio gewechselt: {track.title or 'Track'} "
                        f"({track.duration:.1f}s) — Pacing-Kurve aktualisiert."
                    )

    def _generate_timeline_from_button(self):
        """B-286: Editor-Header-Button 'Timeline generieren'.

        Wenn bereits eine Timeline existiert, vor dem Ueberschreiben einen
        Bestaetigungs-Dialog zeigen (Datenverlust-Schutz fuer ungelockte
        Schnitte). Der Live-Pfad ueber ``pacing_curve.curve_changed`` ruft
        weiterhin direkt ``_generate_timeline`` (kein Confirm pro Kurven-Klick).
        """
        from ui.workspaces.schnitt.regenerate_dialog import confirm_regenerate
        tv = getattr(self.window, "timeline_view", None)
        # M1 Timeline-Virtualisierung (D-066): clip_records ist die Wahrheit —
        # clip_items enthaelt nur die materialisierten Viewport-Items.
        has_timeline = bool(tv is not None and (
            getattr(tv, "clip_records", None) or getattr(tv, "clip_items", None)))
        if has_timeline and not confirm_regenerate(self.window):
            return
        self._generate_timeline()

    def _generate_timeline(self):
        """P8-FREEZE-FIX: Debounced + Worker-based.

        Vorher: Klick in Pacing-Kurve → mouseReleaseEvent → curve_changed
        Signal → DIESE Methode synchron. calculate_cut_points laed Beat-
        Positions aus der DB (grosser JSON-Blob) + macht O(N)-Berechnung
        ueber alle Beats — 4+ Sekunden Main-Thread-Freeze pro Klick.

        Jetzt: 250ms Debounce schluckt Klick-Spam. Der echte Aufruf geht
        in einen Worker-Thread, UI-Updates folgen via finished-Signal.
        """
        from PySide6.QtCore import QTimer
        if not hasattr(self, "_gen_debounce_timer") or self._gen_debounce_timer is None:
            self._gen_debounce_timer = QTimer(self.window)
            self._gen_debounce_timer.setSingleShot(True)
            self._gen_debounce_timer.timeout.connect(self._generate_timeline_impl)
        self._gen_debounce_timer.start(250)

    def _generate_timeline_impl(self):
        from PySide6.QtCore import QObject, Signal, QThread

        if not self._require_schnitt_action("Timeline generieren"):
            return

        # B-284 Phase C / Variante 1 — Editor-Header btn_generate triggert
        # Loading-Overlay (User-Entscheidung 2026-05-09). Worker-progress
        # bridge wird unten durch ctrl.attach_worker(self._cuts_worker)
        # hergestellt; nach worker.done schaltet ctrl._on_done auf
        # refresh_state_from_db zurueck.
        ws = getattr(self.window, "_schnitt_ws", None)
        if ws is not None:
            try:
                ws.enter_loading()
            except Exception as exc:
                logger.debug("schnitt enter_loading failed: %s", exc)

        audio_id = self.window.audio_combo.currentData()
        video_id = self.window.video_combo.currentData()
        densities = self.window.pacing_curve.get_all_densities()
        cut_rate_map = {0: 90, 1: 70, 2: 50, 3: 30, 4: 10}
        tempo_val = cut_rate_map.get(self.window.cut_rate_combo.currentIndex(), 50)
        reactivity = self.window.energy_reactivity_spin.value()

        settings = PacingSettings(
            tempo=tempo_val,
            energy=reactivity,
            cut_density=reactivity,
            vibe=self.window.vibe_input.text(),
            manual_density_curve=densities,
        )

        # Duration-Lookup ist O(1) auf indexed PK — bleibt im Main-Thread
        audio_dur = 0.0
        video_dur = 0.0
        if audio_id is not None:
            with DBSession(engine) as s:
                track = s.get(AudioTrack, audio_id)
                if track and track.duration:
                    audio_dur = track.duration
        if video_id is not None:
            with DBSession(engine) as s:
                clip = s.get(VideoClip, video_id)
                if clip and clip.duration:
                    video_dur = clip.duration

        total_dur = max(audio_dur, video_dur, 30.0)
        self.window.pacing_curve.set_duration(total_dur)

        # P8-FREEZE-FIX: Schwere Berechnung in Worker-Thread.
        # B-172: Sequence-Counter statt requestInterruption (das Worker.run
        # checkt das Flag nie und der Thread hat keine Event-Loop). Alte
        # Worker laufen weiter, ihre Ergebnisse werden im Slot anhand der
        # _gen_seq verworfen.
        self._gen_seq = getattr(self, "_gen_seq", 0) + 1
        my_seq = self._gen_seq
        # B-714: _gen_seq unterscheidet nur Klicks INNERHALB desselben
        # Projekts — ein Projektwechsel erhoeht die Sequenz nicht. Deshalb
        # zusaetzlich die Projekt-Generation zum Start festhalten und im
        # Ergebnis-Slot pruefen. Token-Ermittlung wie im SchnittController
        # (B-714, ui/controllers/schnitt_controller.py): Engine-Identitaet +
        # Engine-URL, weil project_id ueber Projekt-DBs hinweg kollidiert.
        from ui.controllers.schnitt_controller import _current_project_token
        self._gen_project_token = _current_project_token()
        # Alten Thread NICHT mehr blocking abwarten — Qt's parented-thread-
        # Cleanup (parent=self.window) macht das beim Window-Close.

        class _CutsWorker(QObject):
            done = Signal(list, float, int)
            failed = Signal(str, int)
            # Phase 09: Stage-Progress fuer SchnittLoadingView.
            progress = Signal(str, float)

            def __init__(self, audio_id, video_id, settings, total_dur, seq):
                super().__init__()
                self._args = (audio_id, video_id, settings, total_dur)
                self._seq = seq

            def _emit_stage(self, stage_key: str, fraction: float) -> None:
                try:
                    self.progress.emit(stage_key, float(fraction))
                except Exception:
                    pass

            def run(self):
                try:
                    self._emit_stage("cut_calc", 0.1)
                    cuts = calculate_cut_points(*self._args)
                    self._emit_stage("cut_calc", 1.0)
                    self.done.emit(cuts, self._args[3], self._seq)
                except Exception as exc:
                    # B-171: Stacktrace loggen statt nur als Text-Signal.
                    logger.exception(
                        "_CutsWorker crashed (audio_id=%s, video_id=%s)",
                        self._args[0], self._args[1],
                    )
                    self.failed.emit(str(exc), self._seq)

        self._cuts_worker = _CutsWorker(audio_id, video_id, settings, total_dur, my_seq)
        self._cuts_thread = QThread(self.window)
        self._cuts_worker.moveToThread(self._cuts_thread)
        self._cuts_thread.started.connect(self._cuts_worker.run)
        self._cuts_worker.done.connect(self._on_cuts_done)
        self._cuts_worker.failed.connect(self._on_cuts_failed)
        self._cuts_worker.done.connect(self._cuts_thread.quit)
        self._cuts_worker.failed.connect(self._cuts_thread.quit)
        self._cuts_thread.finished.connect(self._cuts_worker.deleteLater)
        # B-284 Phase C — SchnittController-Worker-Bridge.
        # _CutsWorker hat progress/done/failed exakt im erwarteten Schema —
        # attach_worker bindet alle drei direkt.
        ctrl = getattr(self.window, "_schnitt_ctrl", None)
        if ctrl is not None:
            ctrl.attach_worker(self._cuts_worker)
        self._cuts_thread.start()

    def _defer_cut_list_refresh(self) -> None:
        def _refresh():
            try:
                tab_schnitt = self.window._schnitt_ws.editor_view.tab_schnitt
                if hasattr(tab_schnitt, "cut_list_panel"):
                    tab_schnitt.cut_list_panel.set_project(get_active_project_id())
            except Exception as exc:
                logger.debug("cut_list_panel refresh failed: %s", exc)

        QTimer.singleShot(0, _refresh)

    def _defer_schnitt_workspace_refresh(self) -> None:
        def _refresh():
            try:
                ws = getattr(self.window, "_schnitt_ws", None)
                if ws is not None:
                    ws.refresh_state_from_db()
            except Exception as exc:
                logger.debug(
                    "BUG-A: schnitt_ws.refresh_state_from_db nach Auto-Edit fehlgeschlagen: %s",
                    exc,
                )

        QTimer.singleShot(0, _refresh)

    def _cuts_project_changed(self) -> bool:
        """B-714: Laeuft das Cut-Ergebnis in ein anderes Projekt als beim Start?

        ``None`` (Token nicht ermittelbar) schaltet fail-open — gleiche
        Semantik wie ``SchnittController._worker_project_changed``.
        """
        started = getattr(self, "_gen_project_token", None)
        if started is None:
            return False
        from ui.controllers.schnitt_controller import _current_project_token
        now = _current_project_token()
        if now is None:
            return False
        return now != started

    def _discard_foreign_cuts_result(self, kind: str) -> None:
        """B-714: Cut-Ergebnis eines fremden Projekts verwerfen.

        Nur verwerfen, kein Workspace-Resync: derselbe Worker haengt ueber
        ``ctrl.attach_worker`` auch am ``SchnittController``, dessen
        B-714-Guard (``_discard_foreign_project_result``) den Workspace
        bereits aus STATE_LOADING zurueckholt.
        """
        from ui.controllers.schnitt_controller import _current_project_token
        logger.error(
            "_on_cuts_%s: Projekt-Mismatch — Ergebnis gehoert zu Projekt %s, "
            "aktiv ist %s. Ergebnis wird NICHT angewandt (B-714).",
            kind, getattr(self, "_gen_project_token", None),
            _current_project_token(),
        )
        self._gen_project_token = None

    def _on_cuts_done(self, cuts: list, total_dur: float, seq: int = 0):
        # B-020: Worker-Rueckkanal — kann nach dem Fenster-Teardown feuern.
        if not self._window_alive():
            return
        # B-172: stale-result Drop wenn neuerer Klick schon in Flight.
        if seq and seq != getattr(self, "_gen_seq", seq):
            logger.debug("_on_cuts_done: stale seq %d (current %d), ignored.",
                         seq, self._gen_seq)
            return
        # B-714: Projekt-Generations-Guard — die Sequenz allein faengt einen
        # Projektwechsel waehrend der laufenden Berechnung nicht ab.
        if self._cuts_project_changed():
            self._discard_foreign_cuts_result("done")
            return
        beat_times = [cp.time for cp in cuts if cp.source == "beat"]
        self.window.timeline_view.set_beat_markers(beat_times)
        self.window.timeline_view.load_from_db()
        self.window.timeline_view.set_cut_points(cuts, total_dur)

        beat_cuts = sum(1 for c in cuts if c.source == "beat")
        scene_cuts = sum(1 for c in cuts if c.source == "scene")
        energy_cuts = sum(1 for c in cuts if c.source == "energy")
        drum_cuts = sum(1 for c in cuts if c.source == "drum")
        transition_cuts = sum(1 for c in cuts if c.source == "transition")
        drop_cuts = sum(1 for c in cuts if c.source == "drop")
        info_parts = [f"{len(cuts)} Cuts"]
        if beat_cuts: info_parts.append(f"Beat:{beat_cuts}")
        if scene_cuts: info_parts.append(f"Szene:{scene_cuts}")
        if energy_cuts: info_parts.append(f"Energie:{energy_cuts}")
        if drum_cuts: info_parts.append(f"Drum:{drum_cuts}")
        if transition_cuts: info_parts.append(f"DJ-Mix:{transition_cuts}")
        if drop_cuts: info_parts.append(f"Drop:{drop_cuts}")
        info_parts.append(f"{total_dur:.0f}s")
        self.window.cut_info_label.setText(" | ".join(info_parts))
        self.window._mark_dirty()
        self.window.console_text.append(f"[Pacing] {len(cuts)} Cuts generiert (Manual Curve aktiv)")

        # B-598: Finish-Refresh entkoppeln; CutList liest DB synchron.
        self._defer_cut_list_refresh()

    def _on_cuts_failed(self, err: str, seq: int = 0):
        # B-020: Worker-Rueckkanal — kann nach dem Fenster-Teardown feuern.
        if not self._window_alive():
            logger.warning("calculate_cut_points failed (Fenster weg): %s", err)
            return
        # B-172: stale-Fail-Drop
        if seq and seq != getattr(self, "_gen_seq", seq):
            return
        # B-714: gleicher Projekt-Generations-Guard wie in _on_cuts_done.
        if self._cuts_project_changed():
            self._discard_foreign_cuts_result("failed")
            return
        logger.warning("calculate_cut_points failed: %s", err)
        self.window.console_text.append(f"[Pacing-Fehler] {err}")

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        if not self._require_schnitt_action("Auto-Edit"):
            return

        audio_id = self.window.audio_combo.currentData()
        if audio_id is None:
            self.window.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        # Fixplan 2026-07-07 Schritt 7 (V3): Checkbox-markierte Clips sind die
        # manuelle Vorauswahl fuer den Auto-Edit. Ohne Markierung entscheidet
        # die App selbst (ganzer Pool). Ein Timeline-Vorbefuellen ist fuer den
        # Auto-Edit NICHT noetig — er arbeitet auf dem Material-Pool.
        video_ids = self._checked_ids_for_table(self.window.video_pool_table)
        if video_ids:
            self.window.console_text.append(
                f"[Auto-Edit] Manuelle Vorauswahl aktiv: {len(video_ids)} "
                f"markierte Clips werden verwendet."
            )
        else:
            # P9-C: direkt das Source-Model nehmen — der Proxy paginiert und
            # wuerde sonst nur die aktuell sichtbaren 16 Zeilen liefern.
            v_model = getattr(self.window, "video_pool_model", None) or self.window.video_pool_table.model()
            if v_model:
                # Fix (Audit 2026-07-27): rowCount() ist beim Video-Pool
                # gekappt — MediaTableModel(paginated_fetch=True) exponiert
                # initial nur _INITIAL_FETCH_ROWS=100 Zeilen und waechst erst
                # ueber fetchMore() beim Scrollen. Der "keine Auswahl"-Pfad
                # bekam dadurch still nur die ersten 100 Clips als Material-
                # Pool. all_ids() liest wie get_checked_ids() aus _items.
                _all_ids_fn = getattr(v_model, "all_ids", None)
                _all_ids = _all_ids_fn() if callable(_all_ids_fn) else None
                if isinstance(_all_ids, list):
                    video_ids.extend(_all_ids)
                else:
                    for _row in range(v_model.rowCount()):
                        _id_val = v_model.index(_row, 1).data()
                        if _id_val:
                            try:
                                video_ids.append(int(_id_val))
                            except ValueError as exc:
                                logger.warning("_start_auto_edit: failed to parse video clip ID: %s", exc)
            if video_ids:
                self.window.console_text.append(
                    f"[Auto-Edit] Keine Clips markiert — App waehlt "
                    f"automatisch aus allen {len(video_ids)} Clips."
                )

        if not video_ids:
            self.window.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        # B-284 Phase C / Variante 1 — Editor-Header btn_auto_edit triggert
        # Loading-Overlay (User-Entscheidung 2026-05-09). Worker-progress
        # bridge unten ueber ctrl.attach_worker; State-Refresh nach
        # worker.finished via ctrl._on_done.
        #
        # Fix (Audit 2026-07-27): Aufruf stand VOR den Abbruch-Guards oben.
        # Griff einer der Early-Returns (kein Audio / leerer Video-Pool, z.B.
        # waehrend der async Media-Reload noch laeuft), blieb der SCHNITT-
        # Workspace dauerhaft in STATE_LOADING — und
        # SchnittController.set_active_project_protected blockt in dem State
        # jeden Projekt-Push. enter_loading() darf erst feuern, wenn der
        # Worker-Start sicher ist.
        ws = getattr(self.window, "_schnitt_ws", None)
        if ws is not None:
            try:
                ws.enter_loading()
            except Exception as exc:
                logger.debug("schnitt enter_loading failed: %s", exc)

        cut_rate_map = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}
        base_cut_rate = cut_rate_map.get(self.window.cut_rate_combo.currentIndex(), 4)
        breakdown_map = {0: "halve", 1: "force16", 2: "none"}
        breakdown = breakdown_map.get(self.window.breakdown_combo.currentIndex(), "halve")
        anchors = self._collect_anchors_from_ui()

        # NEUBAU-VOLLINTEGRATION T2.1 (USE-007): LLM-Pacing-Schalter aus dem
        # SettingsStore (Checkboxen im Pacing-Panel persistieren dorthin).
        # Vorher gab es repo-weit keinen Setter -> Gates waren toter Code.
        _llm_strategist = False
        _llm_pacing = False
        try:
            from services.settings_store import get_settings_store
            _pstore = get_settings_store()
            # Haken-2-Fix (User 2026-07-17): LLM-Strategist standardmaessig AN.
            # Vorher default=False -> Auto-Edit lief ohne LLM-Pacing, obwohl das
            # gewuenschte Feature. Kostet ~85s LLM-Call (gemma3 auf GPU).
            _llm_strategist = bool(_pstore.get_nested(
                "pacing", "use_llm_strategist", default=True))
            _llm_pacing = bool(_pstore.get_nested(
                "pacing", "use_llm_pacing", default=False))
        except Exception as exc:
            logger.debug("LLM-Pacing-Settings nicht lesbar: %s", exc)

        # AUDIT-FIXPLAN A1 (Merge 2026-07-08): transition_combo auslesen und
        # in DB persistieren
        transition_type = "cut" if self.window.transition_combo.currentIndex() == 1 else "crossfade"
        try:
            from database import nullpool_session, Project
            from database import get_active_project_id
            pid = get_active_project_id()
            if pid:
                with nullpool_session() as session:
                    proj = session.get(Project, pid)
                    if proj:
                        proj.transition_type = transition_type
        except Exception as db_exc:
            logger.warning("_auto_edit_to_beat: transition_type konnte nicht in DB persistiert werden: %s", db_exc)

        settings = AdvancedPacingSettings(
            base_cut_rate=base_cut_rate,
            energy_reactivity=self.window.energy_reactivity_spin.value(),
            breakdown_behavior=breakdown,
            vibe=self.window.vibe_input.text(),
            manual_density_curve=self.window.pacing_curve.get_all_densities(),
            anchors=anchors,
            use_llm_strategist=_llm_strategist,
            use_llm_pacing=_llm_pacing,
            transition_type=transition_type,
        )
        if _llm_strategist or _llm_pacing:
            self.window.console_text.append(
                f"[Auto-Edit] LLM-Pacing aktiv: Strategist={_llm_strategist}, "
                f"EDL-Pacing={_llm_pacing} (Ollama)."
            )

        self.window.console_text.append(
            f"[Auto-Edit] Phase 3 DJ-Pacing starte "
            f"(Rate={base_cut_rate} Beats, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}, {len(video_ids)} Clips, "
            f"{len(anchors)} Anker)..."
        )
        self.window.btn_auto_edit.setEnabled(False)
        self.window.btn_auto_edit.setText("laeuft...")

        # K11 FIX: engine.dispose() ENTFERNT — schloss ALLE Pool-Connections
        # inklusive derer von anderen Threads (z.B. laufende Analysen).
        # QueuePool-Exhaustion wird durch korrekte Session-Nutzung (with-Blocks)
        # und nullpool_session() fuer Worker-Threads verhindert.

        self.start_auto_edit_worker(
            audio_id=int(audio_id),
            video_ids=video_ids,
            settings=settings,
            task_name="Auto-Edit (Phase 3)",
            task_description=(
                f"DJ-Pacing: {base_cut_rate}-Beat, "
                f"Reaktivitaet={settings.energy_reactivity}%, Breakdown={breakdown}"
            ),
        )

    def start_auto_edit_worker(
        self,
        *,
        audio_id: int,
        video_ids: list[int],
        settings: AdvancedPacingSettings,
        task_name: str = "Auto-Edit (Phase 3)",
        task_description: str = "DJ-Pacing",
    ):
        """Start Auto-Edit and route results through the real timeline finish path."""
        tm = GlobalTaskManager.instance()
        task = tm.create_task(task_name, task_description)
        worker = AutoEditWorker(audio_id, video_ids, settings)
        worker.task_id = task.task_id
        # B-795: Projekt-Token beim START festhalten. `_on_auto_edit_finished`
        # hat die Projekt-ID bisher erst beim Eintreffen des Ergebnisses
        # gelesen — ein Projektwechsel waehrend des Laufs schrieb das Ergebnis
        # des alten Projekts in die Timeline des neuen. Gleiches Muster wie
        # der B-714-Guard fuer den Cuts-Worker.
        from ui.controllers.schnitt_controller import _current_project_token
        self._auto_edit_project_token = _current_project_token()
        # B-284 Phase C — SchnittController-Worker-Bridge.
        # AutoEditWorker hat kein `done`/`failed`, nur `finished(list,list)`.
        # attach_worker bindet `progress` an `workspace.show_progress`;
        # State-Refresh nach Ende erfolgt zusaetzlich ueber `finished`.
        ctrl = getattr(self.window, "_schnitt_ctrl", None)
        if ctrl is not None:
            ctrl.attach_worker(worker)
            try:
                worker.finished.connect(lambda *_a: ctrl._on_done())
            except Exception as exc:
                logger.debug("attach_worker finished bridge failed: %s", exc)
        self.window.worker_dispatcher._start_worker_thread(
            worker,
            on_finish=lambda segs, cps: self._on_auto_edit_finished(
                segs, cps, task.task_id, audio_id_override=audio_id
            ),
            on_error=lambda err: self._on_auto_edit_error(err, task.task_id),
        )
        return task

    def _on_auto_edit_finished(
        self,
        segments: list,
        cut_points: list,
        task_id: str,
        audio_id_override: int | None = None,
    ):
        self.window.btn_auto_edit.setEnabled(True)
        self.window.btn_auto_edit.setText("Auto-Edit")

        if not segments:
            if not cut_points:
                self.window.console_text.append("[Auto-Edit] Keine Segmente erzeugt.")
                task_manager.finish_task(task_id, "error", "Keine Segmente")
                return
            self.window.console_text.append("[Auto-Edit] Keine Segmente erzeugt (kein Audio/Beats?).")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        _degraded = any(seg.get("degraded", False) for seg in segments)
        if _degraded:
            # B2: Warntext nach tatsaechlicher Ursache differenzieren — vorher
            # stand hier pauschal "SigLIP", auch wenn der Beat-Fallback der
            # Ausloeser war.
            _reason = next(
                (seg.get("degraded_reason", "") for seg in segments if seg.get("degraded")),
                "",
            )
            _msgs = []
            if "siglip" in _reason:
                _msgs.append(
                    "SigLIP-Modell konnte nicht geladen werden — "
                    "kein semantisches Audio-Video-Matching."
                )
            if "beat_fallback" in _reason:
                _msgs.append(
                    "Beat-Analyse lief im Fallback-Modus — "
                    "Beatgrid ist synthetisch (aus BPM) oder ohne beat_this erzeugt."
                )
            if not _msgs:
                _msgs.append(
                    "Der Auto-Edit wurde im degradierten Modus erzeugt (Ursache unbekannt)."
                )
            _detail = " ".join(_msgs)
            self.window.console_text.append(
                "<span style='color: #ff3333; font-weight: bold;'>"
                f"[WARNUNG] Auto-Edit degradiert: {_detail}"
                "</span>"
            )
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.window,
                "Auto-Edit Degradiert",
                "\n\n".join(_msgs)
                + "\n\nDer Auto-Edit wurde im degradierten Modus erzeugt.",
            )

        # B-795: Ergebnis nur anwenden, wenn es noch zum Projekt gehoert, fuer
        # das der Lauf gestartet wurde. Sonst schreibt ein Auto-Edit des alten
        # Projekts stillschweigend in die Timeline des neuen — das sieht wie
        # ein normales Ergebnis aus und ist deshalb besonders tueckisch.
        # Fail-open bei fehlendem Token, wie beim B-714-Guard.
        _started_token = getattr(self, "_auto_edit_project_token", None)
        if _started_token is not None:
            from ui.controllers.schnitt_controller import _current_project_token
            _now_token = _current_project_token()
            if _now_token is not None and _now_token != _started_token:
                logger.warning(
                    "B-795: Auto-Edit-Ergebnis verworfen — Projekt gewechselt "
                    "(Start=%s, jetzt=%s).", _started_token, _now_token,
                )
                self.window.console_text.append(
                    "[Auto-Edit] Ergebnis verworfen: waehrend des Laufs wurde "
                    "das Projekt gewechselt."
                )
                task_manager.finish_task(task_id, "error", "Projekt gewechselt")
                self._auto_edit_project_token = None
                return

        from ui.undo_commands import ApplyAutoEditCommand
        project_id = get_active_project_id()
        cmd = ApplyAutoEditCommand(
            timeline=self.window.timeline_view,
            project_id=project_id,
            new_segments=segments,
        )
        self.window.timeline_view.undo_stack.push(cmd)

        # B-784: Brain-V3-Lernzustand direkt nach dem Apply nachziehen. Ohne
        # diesen Aufruf schreibt niemand ``timeline_cuts`` in
        # ``brain_v3/state.db`` — ``BrainV3Service.learning_session`` faellt dann
        # immer auf den Weight-Bucket-Sampler ohne Medienpfade zurueck und
        # B-732/B-733/B-781 wirken live nicht.
        self._start_brain_learning_sync(project_id)

        # Fixplan 2026-07-07 Schritt 7/7c: Verwendungs-Markierung im
        # MATERIAL-Pool (Tabelle gruen vs. ausgegraut, Grid-Badges,
        # sichtbares Hinweis-Label).
        try:
            usage: dict[int, int] = {}
            for seg in segments:
                mid = seg.get("media_id", seg.get("video_id"))
                if mid is not None:
                    usage[int(mid)] = usage.get(int(mid), 0) + 1
            self._refresh_timeline_usage_marking(
                usage,
                extra=f"Auto-Edit: {len(segments)} Segmente beat-genau gesetzt.",
            )
            self.window.console_text.append(
                f"[Auto-Edit] {len(segments)} Segmente aus "
                f"{len(usage)} verschiedenen Clips — verwendete Clips sind "
                f"im MATERIAL-Pool gruen markiert."
            )
        except Exception as exc:
            logger.warning("Auto-Edit Usage-Markierung fehlgeschlagen: %s", exc)

        # Fixplan 2026-07-07 Schritt 8: nach Auto-Edit die Timeline auf den
        # Inhalt einpassen (NLE-Konvention; ersetzt den manuellen Fit-Klick).
        try:
            self.window.timeline_view.fit_to_content()
        except Exception as exc:
            logger.debug("fit_to_content nach Auto-Edit fehlgeschlagen: %s", exc)

        try:
            self._build_otio_timeline(segments, audio_id=audio_id_override)
        except Exception as exc:
            logger.warning("OTIO export failed: %s", exc)
            if hasattr(self.window, "console_text"):
                self.window.console_text.append(f"[OTIO] Export-Fehler: {exc}")

        if cut_points:
            total_dur = segments[-1]["end"] if segments else 60.0
            cps = [CutPoint(
                time=cp["time"], source=cp["source"], strength=cp["strength"]
            ) for cp in cut_points]
            beat_times = [cp["time"] for cp in cut_points if cp["source"] == "beat"]
            self.window.timeline_view.set_beat_markers(beat_times)
            self.window.timeline_view.set_cut_points(cps, total_dur)

            anchor_cuts = sum(1 for cp in cut_points if cp["source"] == "anchor")
            beat_cuts = sum(1 for cp in cut_points if cp["source"] == "beat")
            transition_cuts = sum(1 for cp in cut_points if cp["source"] == "transition")
            drop_cuts = sum(1 for cp in cut_points if cp["source"] == "drop")
            parts = [f"{len(cut_points)} Cuts", f"Beat:{beat_cuts}"]
            if anchor_cuts: parts.append(f"Anker:{anchor_cuts}")
            if transition_cuts: parts.append(f"DJ-Mix:{transition_cuts}")
            if drop_cuts: parts.append(f"Drop:{drop_cuts}")
            parts.append(f"{total_dur:.0f}s | {len(segments)} Segmente")
            self.window.cut_info_label.setText(" | ".join(parts))

        self.window._mark_dirty()
        self.window.console_text.append(
            f"[Auto-Edit] Phase 3 fertig: {len(segments)} Segmente, OTIO Timeline generiert."
        )
        task_manager.finish_task(task_id, "finished", f"{len(segments)} Segmente")

        try:
            from services.pacing.bridge import use_studio_brain_pipeline

            if use_studio_brain_pipeline():
                audio_id = audio_id_override
                if audio_id is None:
                    audio_id = self.window.audio_combo.currentData()
                run_id = self._latest_mem_pacing_run_id(audio_id)
                if hasattr(self.window.timeline_view, "set_active_pacing_run"):
                    self.window.timeline_view.set_active_pacing_run(run_id)
                if run_id is not None and hasattr(self.window, "console_text"):
                    self.window.console_text.append(
                        f"[Brain] Feedback aktiv fuer mem_pacing_run #{run_id}."
                    )
        except Exception as exc:
            logger.debug("active pacing run setup failed: %s", exc)

        # B-598: Finish-Refreshes entkoppeln; beide koennen DB synchron lesen.
        self._defer_cut_list_refresh()

        # BUG-A Fix: SchnittWorkspace nach Auto-Edit auf Editor-State umschalten
        self._defer_schnitt_workspace_refresh()

    def _start_brain_learning_sync(self, project_id: int | None):
        """B-784: ``timeline_cuts`` in ``brain_v3/state.db`` nachziehen.

        Off-thread, weil dieser Pfad im GUI-Thread laeuft: ``AutoEditWorker``
        liefert ueber ``worker_dispatcher._start_worker_thread`` mit
        ``Qt.QueuedConnection`` ab, ``_on_auto_edit_finished`` ist also die
        Event-Loop des GUI-Threads. Der Sync liest die ``mem_decision``-Zeilen
        des juengsten Runs und schreibt pro Cut eine Zeile — bei einem
        DJ-Mix sind das vierstellig viele.

        Fehler bleiben folgenlos: der Apply ist zu diesem Zeitpunkt bereits
        durch, der Lernzustand ist Zusatznutzen.

        Returns:
            Den gestarteten Thread, sonst ``None``.
        """
        try:
            from services.brain import timeline_state as _timeline_state

            # Zwei Auto-Edits kurz hintereinander wuerden sonst zwei Syncs
            # gleichzeitig auf dieselbe state.db schreiben — SQLite quittiert
            # das mit "database is locked", und der zweite Lauf ginge
            # verloren. Laeuft noch einer, ueberspringen: er schreibt ohnehin
            # den aktuellen Timeline-Stand.
            _running = getattr(self, "_brain_learning_sync_thread", None)
            if _running is not None and _running.is_alive():
                logger.info(
                    "B-784: Lern-Sync laeuft bereits — kein zweiter Start.")
                return None

            thread = threading.Thread(
                target=_timeline_state.sync_current_timeline_after_apply,
                kwargs={"project_id": project_id},
                name="brain-v3-learning-sync",
                daemon=True,
            )
            thread.start()
            self._brain_learning_sync_thread = thread
            return thread
        except Exception as exc:  # broad: darf den Apply nie brechen
            logger.warning(
                "B-784: Brain-V3-Lern-Sync konnte nicht gestartet werden: %s", exc)
            return None

    def _latest_mem_pacing_run_id(self, audio_id: int | None) -> int | None:
        if audio_id is None:
            return None
        with DBSession(engine) as session:
            row = session.execute(
                text(
                    "SELECT id FROM mem_pacing_run "
                    "WHERE audio_track_id = :audio_id "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"audio_id": int(audio_id)},
            ).fetchone()
            return int(row[0]) if row is not None else None

    def _build_otio_timeline(self, segments: list, audio_id: int | None = None):
        if audio_id is None:
            audio_id = self.window.audio_combo.currentData()
        tls = TimelineService(fps=30.0)
        tls.create_timeline("PB Studio Auto-Edit")

        if audio_id is not None:
            with DBSession(engine) as session:
                # B-622: column-select statt session.get(AudioTrack) — vermeidet
                # eager beatgrid/waveform_data-Blobs (lazy='joined'), 42s-Freeze.
                track = session.execute(
                    select(
                        AudioTrack.title,
                        AudioTrack.file_path,
                        AudioTrack.duration,
                    ).where(AudioTrack.id == audio_id)
                ).first()
                if track:
                    audio_track = tls.get_audio_track()
                    tls.add_clip(
                        track=audio_track,
                        name=track.title or Path(track.file_path).stem,
                        media_path=track.file_path,
                        source_start=0.0,
                        source_duration=track.duration or 60.0,
                        available_duration=track.duration,
                    )

        video_track = tls.get_video_track()
        for seg in segments:
            source_duration = max(
                0.04,
                seg.get("source_end", seg["end"]) - seg.get("source_start", seg["start"]),
            )
            metadata = {}
            if seg.get("is_anchor"):
                metadata = {"scene_id": seg.get("scene_id", ""), "type": "anchor"}

            tls.add_clip(
                track=video_track,
                name=Path(seg["video_path"]).stem if seg.get("video_path") else f"clip_{seg['video_id']}",
                media_path=seg.get("video_path", ""),
                source_start=seg.get("source_start", 0.0),
                source_duration=source_duration,
                metadata=metadata if metadata else None,
            )

        anchors = self._collect_anchors_from_ui()
        for anchor in anchors:
            tls.add_marker(
                name=f"Anchor_{anchor['scene_id']}",
                time=anchor["time"],
                color="MAGENTA",
                metadata={
                    "scene_id": anchor["scene_id"],
                    "type": "anchor",
                },
            )

        self.window._otio_timeline_service = tls
        otio_path = tls.save_otio("exports/auto_edit_phase3.otio")
        self.window.console_text.append(f"[OTIO] Timeline gespeichert: {otio_path}")

    def _on_auto_edit_error(self, error_msg: str, task_id: str):
        self.window.btn_auto_edit.setEnabled(True)
        self.window.btn_auto_edit.setText("Auto-Edit")
        self.window.console_text.append(f"[Auto-Edit Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    def _collect_anchors_from_ui(self) -> list[dict]:
        anchors = []
        for i in range(self.window.anchor_list.topLevelItemCount()):
            item = self.window.anchor_list.topLevelItem(i)
            time_text = item.text(0)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole) or ""
            try:
                if ":" in time_text:
                    parts = time_text.replace("s", "").split(":")
                    time_sec = float(parts[0]) * 60 + float(parts[1])
                else:
                    time_sec = float(time_text.replace("s", ""))
                anchors.append({"time": time_sec, "scene_id": str(scene_id)})
            except (ValueError, IndexError):
                continue
        return anchors

    def _add_anchor_dialog(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Anker hinzufuegen")
        dialog.setFixedSize(320, 180)
        dialog.setStyleSheet("background-color: #161c26; color: #e8e6e3;")
        layout = QVBoxLayout(dialog)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Zeitpunkt (Sek):"))
        time_spin = QDoubleSpinBox()
        time_spin.setRange(0.0, 36000.0)
        time_spin.setDecimals(3)
        time_spin.setSingleStep(0.1)
        time_spin.setValue(0.0)
        time_spin.setSuffix("s")
        time_spin.setToolTip(
            "Zeitpunkt des neuen Sync-Ankers in Sekunden auf der Audio-Timeline."
        )
        time_row.addWidget(time_spin)
        layout.addLayout(time_row)

        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Video/Szene:"))
        scene_combo = QComboBox()
        scene_combo.addItem("-- Szene waehlen --", "")
        scene_combo.setToolTip(
            "Video oder erkannte Szene auswaehlen, die am Ankerzeitpunkt synchronisiert werden soll."
        )
        try:
            with DBSession(engine) as session:
                # B-633: column-select statt joinedload(VideoClip.scenes) — laed
                # keine Scene-JSON-Blobs (keyframe_paths/embedding_indices/ai_*),
                # die den GUI-Thread beim Dialog-Oeffnen ~13s einfroren. Nur die
                # genutzten Skalar-Spalten; outerjoin erhaelt Clips ohne Scenes.
                rows = session.execute(
                    select(
                        VideoClip.id, VideoClip.file_path,
                        Scene.id, Scene.start_time, Scene.end_time,
                    )
                    .outerjoin(Scene, Scene.video_clip_id == VideoClip.id)
                    .where(
                        VideoClip.project_id == get_active_project_id(),
                        VideoClip.deleted_at.is_(None),
                    )
                ).all()
                # Nach Clip gruppieren (insertion order), Szenen sammeln.
                clips_map: dict = {}
                for clip_id, clip_path, scene_id, s_start, s_end in rows:
                    entry = clips_map.get(clip_id)
                    if entry is None:
                        entry = {"path": clip_path, "scenes": []}
                        clips_map[clip_id] = entry
                    if scene_id is not None:
                        entry["scenes"].append((scene_id, s_start, s_end))
                for clip_id, entry in clips_map.items():
                    clip_name = Path(entry["path"]).stem[:20]
                    for scene_id, s_start, s_end in entry["scenes"]:
                        label = f"{clip_name} | Szene {scene_id} ({s_start:.1f}-{s_end:.1f}s)"
                        scene_combo.addItem(label, str(scene_id))
                    if not entry["scenes"]:
                        scene_combo.addItem(f"{clip_name} (komplett)", f"clip_{clip_id}")
        except Exception as exc:
            logger.warning("_add_anchor_dialog: DB error loading scenes: %s", exc)
        scene_row.addWidget(scene_combo)
        layout.addLayout(scene_row)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Hinzufuegen")
        btn_ok.setObjectName("btn_accent")
        btn_ok.setToolTip(
            "Anker mit gewaehlter Zeit und Szene zur Liste hinzufuegen."
        )
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setToolTip(
            "Anker-Dialog schliessen, ohne einen neuen Anker zu speichern."
        )
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            time_sec = time_spin.value()
            scene_id = scene_combo.currentData() or ""
            scene_label = scene_combo.currentText()
            minutes = int(time_sec // 60)
            secs = time_sec % 60
            time_str = f"{minutes}:{secs:05.2f}"
            item = QTreeWidgetItem([time_str, scene_label[:30]])
            item.setData(0, Qt.ItemDataRole.UserRole, scene_id)
            self.window.anchor_list.addTopLevelItem(item)
            self.window.console_text.append(f"[Anchor] Anker bei {time_str} -> {scene_label}")

    def _remove_selected_anchor(self):
        selected = self.window.anchor_list.currentItem()
        if selected:
            idx = self.window.anchor_list.indexOfTopLevelItem(selected)
            self.window.anchor_list.takeTopLevelItem(idx)
            self.window.console_text.append("[Anchor] Anker entfernt.")

    def _populate_anchor_list_from_db(self):
        """B-634: Befuellt die anchor_list-QTreeWidget beim Projekt-Load mit den
        persistierten Dialog-Ankern (``AudioVideoAnchor`` mit
        ``anchor_type="dialog"``) des aktiven Projekts.

        B-619 Symmetrie-Fix: Liest auch video_time aus und loest dies ueber einen
        SQL outerjoin mit Scene wieder auf die originalen scene_ids auf, damit
        nachfolgende Sync-Operationen keine verfaelschten IDs lesen.
        """
        tree = getattr(self.window, "anchor_list", None)
        if tree is None:
            return
        pid = get_active_project_id()
        rows = []
        if pid is not None:
            try:
                from sqlalchemy import and_, func, select
                from database import nullpool_session, AudioVideoAnchor, AudioTrack, Scene
                with nullpool_session() as session:
                    rows = session.execute(
                        select(
                            AudioVideoAnchor.audio_time,
                            AudioVideoAnchor.video_clip_id,
                            AudioVideoAnchor.video_time,
                            Scene.id,
                        )
                        .join(
                            AudioTrack,
                            AudioVideoAnchor.audio_track_id == AudioTrack.id,
                        )
                        .outerjoin(
                            Scene,
                            and_(
                                Scene.video_clip_id == AudioVideoAnchor.video_clip_id,
                                func.abs(Scene.start_time - AudioVideoAnchor.video_time) < 1e-3
                            )
                        )
                        .where(
                            AudioTrack.project_id == pid,
                            AudioVideoAnchor.anchor_type == "dialog",
                        )
                        .order_by(AudioVideoAnchor.audio_time)
                    ).all()
            except Exception as exc:
                logger.warning("_populate_anchor_list_from_db: DB-Fehler: %s", exc)
                rows = []
        tree.clear()
        for audio_time, video_clip_id, video_time, scene_id in rows:
            if audio_time is None:
                continue
            minutes = int(audio_time // 60)
            secs = audio_time % 60
            time_str = f"{minutes}:{secs:05.2f}"
            
            if scene_id is not None:
                user_role_val = str(scene_id)
                label = f"Szene {scene_id} (Clip {video_clip_id})"
            else:
                user_role_val = f"clip_{video_clip_id}" if video_clip_id is not None else ""
                label = f"Clip {video_clip_id}" if video_clip_id is not None else "Unbekannt"

            item = QTreeWidgetItem([time_str, label[:30]])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                user_role_val,
            )
            tree.addTopLevelItem(item)

    def _collect_dialog_anchors(self):
        """B-619: Liest die Dialog-Anker aus der anchor_list-QTreeWidget.

        Rueckgabe: Liste ``[{"audio_time": float, "scene_id": str}, ...]``.
        Zeit-Format der Items ist "M:SS.ss" (siehe _add_anchor_dialog); scene_id
        steckt in UserRole von Spalte 0.
        """
        anchors = []
        tree = self.window.anchor_list
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            time_text = item.text(0)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole)
            try:
                if ":" in str(time_text):
                    parts = str(time_text).split(":")
                    audio_time = int(parts[0]) * 60 + float(parts[1])
                else:
                    audio_time = float(time_text)
            except (ValueError, IndexError):
                logger.warning("_collect_dialog_anchors: Zeit nicht parsebar: %r", time_text)
                continue
            anchors.append({"audio_time": audio_time, "scene_id": scene_id or ""})
        return anchors

    def _sync_anchors(self):
        # B-619: NEUER Pfad — Dialog-Anker (anchor_list) in AudioVideoAnchor
        # persistieren. Getrennt vom M-Tasten-Sync (timeline_view.sync_anchors).
        dialog_count = None
        audio_id = self.window.audio_combo.currentData()
        dialog_anchors = self._collect_dialog_anchors()
        if dialog_anchors:
            if audio_id is None:
                self.window.console_text.append("[Anchor] Kein Audio-Track ausgewaehlt — Dialog-Anker koennen nicht gespeichert werden.")
            else:
                try:
                    from services.anchor_sync_service import sync_dialog_anchors
                    dialog_count = sync_dialog_anchors(audio_id, dialog_anchors)
                    skipped = len(dialog_anchors) - dialog_count
                    msg = f"[Anchor] {dialog_count} Dialog-Anker synchronisiert (AudioVideoAnchor)."
                    if skipped:
                        msg += f" {skipped} ohne aufloesbare Szene uebersprungen."
                    self.window.console_text.append(msg)
                except Exception as exc:
                    logger.error("_sync_anchors: Dialog-Anker-Persistenz fehlgeschlagen: %s", exc, exc_info=True)
                    self.window.console_text.append(f"[Anchor] Fehler beim Speichern der Dialog-Anker: {exc}")

        # Bestehender M-Tasten-Anker-Sync — Verhalten unveraendert.
        synced = self.window.timeline_view.sync_anchors()
        if synced:
            self.window.timeline_view.load_from_db()
            self.window.console_text.append("[Anchor] Timeline-Anker (M) synchronisiert — Video-Clips an Audio-Ankern ausgerichtet.")

        # B-619 Folge: Wurden NUR Dialog-Anker persistiert (kein M-Sync), loest
        # der Zweig oben keinen Reload aus -> die neuen Dialog-Marker blieben
        # unsichtbar. Additiver Reload nur in diesem Fall (bei synced hat der
        # M-Zweig bereits neu geladen und zeigt die Dialog-Marker mit).
        if dialog_count and not synced:
            self.window.timeline_view.load_from_db()

        if dialog_count is None and not synced:
            self.window.console_text.append("[Anchor] Keine Anker gefunden. Lege Anker per '+Anker' an oder setze Timeline-Anker (Rechtsklick oder Taste M), dann klicke erneut.")

    def _learn_anchor_as_ai_rule(self):
        selected = self.window.anchor_list.currentItem()
        if not selected:
            self.window.console_text.append("[KI-Gedaechtnis] Kein Anker ausgewaehlt.")
            return
        audio_id = self.window.audio_combo.currentData()
        if audio_id is None:
            self.window.console_text.append("[KI-Gedaechtnis] Kein Audio-Track ausgewaehlt.")
            return
        time_text = selected.text(0)
        scene_id_raw = selected.data(0, Qt.ItemDataRole.UserRole)
        try:
            if ":" in str(time_text):
                parts = str(time_text).split(":")
                anchor_time = int(parts[0]) * 60 + float(parts[1])
            else:
                anchor_time = float(time_text)
        except (ValueError, IndexError):
            self.window.console_text.append("[KI-Gedaechtnis] Fehler beim Parsen der Anker-Zeit.")
            return
        try:
            scene_int = int(scene_id_raw) if scene_id_raw else None
        except (ValueError, TypeError):
            scene_int = None

        from services.pacing_service import learn_from_anchor
        success = learn_from_anchor(audio_id, anchor_time, scene_int, f"Anker@{time_text}")
        if success:
            self.window.console_text.append(f"[KI-Gedaechtnis] Regel gelernt: {time_text} — Wird beim naechsten Auto-Edit beruecksichtigt.")
            self.window.btn_learn_ai.setStyleSheet("background-color: #4ade80; color: #0a0d12; font-weight: 800; font-size: 10px; border-radius: 3px;")
            def _reset_btn():
                if self.window and self.window.isVisible():
                    self.window.btn_learn_ai.setStyleSheet(
                        "background-color: #d4a44a; color: #0a0d12; "
                        "font-weight: 800; font-size: 10px; border-radius: 3px;"
                    )
            
            QTimer.singleShot(2000, _reset_btn)
        else:
            self.window.console_text.append("[KI-Gedaechtnis] Fehler beim Speichern der Regel.")

    def _rl_feedback_positive(self):
        self._save_rl_feedback("positive")

    def _rl_feedback_negative(self):
        self._save_rl_feedback("negative")

    def _save_rl_feedback(self, sentiment: str):
        from services.pacing_service import record_rl_feedback
        audio_id = self.window.audio_combo.currentData()
        if audio_id is None:
            self.window.console_text.append(f"[RL-Feedback] {sentiment} - Kein Audio-Track gewaehlt.")
            return
        success = record_rl_feedback(audio_id, sentiment, get_active_project_id())
        if success:
            emoji = "\U0001f44d" if sentiment == "positive" else "\U0001f44e"
            self.window.console_text.append(f"[RL-Feedback] {emoji} {sentiment.title()} gespeichert")
            self.window.statusBar().showMessage(f"RL-Feedback: {sentiment.title()} gespeichert", 3000)
        else:
            self.window.console_text.append(f"[RL-Feedback] Fehler beim Speichern")

    def _apply_style_preset(self, index: int):
        """Tier-3-Sunset T3.8: Liest jetzt vom Pacing-&-Anker-Sub-Tab statt vom
        hidden EditWorkspace-Host."""
        from database import engine, StylePreset
        from sqlalchemy.orm import Session as DBSession
        pacing_tab = self.window._schnitt_ws.editor_view.tab_pacing_anker
        preset_name = pacing_tab.style_combo.currentText()
        if not preset_name:
            return
        try:
            with DBSession(engine) as session:
                preset = session.query(StylePreset).filter_by(name=preset_name).first()
                if not preset:
                    return
                cut_rate_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}
                closest_beat = min(cut_rate_map.keys(), key=lambda x: abs(x - preset.cut_rate))
                pacing_tab.cut_rate_combo.setCurrentIndex(cut_rate_map.get(closest_beat, 2))
                pacing_tab.reactivity_slider.setValue(int(preset.energy_reactivity * 100))
                breakdown_map = {"halve": 0, "16beat": 1, "none": 2}
                pacing_tab.breakdown_combo.setCurrentIndex(breakdown_map.get(preset.breakdown_behavior, 0))
                self.window.console_text.append(f"[Style-Preset] '{preset_name}' angewendet.")
                self.window.statusBar().showMessage(f"Style-Preset '{preset_name}' angewendet", 3000)
        except Exception as e:
            self.window.console_text.append(f"[Style-Preset] Fehler: {e}")

    def _show_keyframe_strings(self):
        # B-647: DB-Load + String-Bau liefen synchron im GUI-Thread und froren
        # die App bei grossen Projekten ~6s ein (WATCHDOG-Beleg 2026-07-17).
        # Jetzt via BaseWorker/run_worker off-thread, Ergebnis per Signal.
        from workers.base import BaseWorker, run_worker

        project_id = get_active_project_id()
        self.window.keyframe_text.setPlainText("Generiere Keyframe-Strings ...")

        # B-794: Projekt-Token beim Start festhalten. Ohne den Abgleich unten
        # landet das Ergebnis eines Laufs im Textfeld des inzwischen
        # gewechselten Projekts. Gleiches Muster wie B-714/B-795.
        from ui.controllers.schnitt_controller import _current_project_token
        _started_token = _current_project_token()

        def _project_changed() -> bool:
            if _started_token is None:
                return False  # fail-open, wie beim B-714-Guard
            _now = _current_project_token()
            return _now is not None and _now != _started_token

        class _KeyframeStringsWorker(BaseWorker):
            def _do_work(self):
                return generate_keyframe_strings_for_project(project_id=project_id)

        def _on_finish(kf_string):
            if _project_changed():
                logger.warning("B-794: Keyframe-Strings verworfen — Projekt gewechselt.")
                return
            self.window.keyframe_text.setPlainText(kf_string or "")
            self.window.console_text.append("[Pacing] Keyframe-Strings generiert.")

        def _on_error(err_msg):
            if _project_changed():
                logger.warning("B-794: Keyframe-Fehlermeldung verworfen — Projekt gewechselt.")
                return
            self.window.keyframe_text.setPlainText(f"Fehler: {err_msg}")
            self.window.console_text.append(f"[Pacing-Fehler] Keyframe-Strings: {err_msg}")

        run_worker(self.window, _KeyframeStringsWorker(),
                   on_finish=_on_finish, on_error=_on_error)

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.window._mark_dirty()
        self.window.console_text.append(f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s")

    # ------------------------------------------------------------------
    # SchnittController-Bridge (B-284 Phase A — 2026-05-09)
    # PacingProfileBinder im SchnittController spiegelt cut_rate / style /
    # reactivity / breakdown / vibe bereits in die UI. Adapter-Slots rufen
    # daher die bestehenden Worker-Pfade direkt; das Profile-Argument bleibt
    # vorerst Marker fuer Folge-Refactor (Profile direkt statt Widget-Lookup).
    # ------------------------------------------------------------------
    def _ensure_combos_filled_from_project(self) -> bool:
        """B-294: Wenn audio_combo/video_combo leer, erstes Audio + erstes Video
        aus Project-DB ziehen. Returnt True wenn beide befuellt sind.

        Notwendig weil im SCHNITT-Empty-State die Combos unsichtbar sind —
        Preset-Klick wuerde sonst in _auto_edit_to_beat silent returnen.
        """
        from database import engine, AudioTrack, VideoClip, get_active_project_id
        from sqlalchemy.orm import Session as DBSession

        pid = get_active_project_id()
        if pid is None:
            return False
        try:
            with DBSession(engine) as s:
                # B-090: nur die ID selektieren, nicht das ORM-Objekt. Gebraucht
                # wird ausschliesslich .id (findData unten); ein Voll-Laden zoege
                # ueber lazy='joined' die Beatgrid-/Waveform-JSON-Blobs mit bzw.
                # ueber lazy='selectin' saemtliche Scenes des Clips. Dieser Guard
                # laeuft laut Docstring zwingend auf dem Qt-Main-Thread (Pre-Flight
                # VOR dem Worker-Start) — der Blob-Load blockierte also die GUI.
                if self.window.audio_combo.currentData() is None:
                    first_audio_id = (
                        s.query(AudioTrack.id)
                        .filter_by(project_id=pid)
                        .filter(AudioTrack.deleted_at.is_(None))
                        .order_by(AudioTrack.id)
                        .scalar()
                    )
                    if first_audio_id is not None:
                        idx = self.window.audio_combo.findData(first_audio_id)
                        if idx >= 0:
                            self.window.audio_combo.setCurrentIndex(idx)
                if self.window.video_combo.currentData() is None:
                    first_video_id = (
                        s.query(VideoClip.id)
                        .filter_by(project_id=pid)
                        .filter(VideoClip.deleted_at.is_(None))
                        .order_by(VideoClip.id)
                        .scalar()
                    )
                    if first_video_id is not None:
                        idx = self.window.video_combo.findData(first_video_id)
                        if idx >= 0:
                            self.window.video_combo.setCurrentIndex(idx)
        except (RuntimeError, AttributeError) as exc:
            # I-3: AttributeError signalisiert Programmierfehler (Combo-Widget
            # fehlt) — nicht schlucken, eskalieren statt False zu maskieren.
            if isinstance(exc, AttributeError):
                raise
            logger.warning(
                "B-294 _ensure_combos_filled_from_project (runtime): %s", exc
            )
            return False
        except Exception as exc:
            # I-3: SQLAlchemyError + sonstige DB-Probleme: geloggt, False
            # zurueck — UI bleibt funktionsfaehig, Adapter zeigt Console-Hint.
            logger.warning(
                "B-294 _ensure_combos_filled_from_project (db): %s", exc
            )
            return False
        return (
            self.window.audio_combo.currentData() is not None
            and self.window.video_combo.currentData() is not None
        )

    def _guard_combos_or_notify(self, feature: str) -> bool:
        """B-294/M-1: gemeinsame Pre-Flight-Guard fuer SCHNITT-Adapter-Slots.

        Wenn _ensure_combos_filled_from_project False zurueckgibt, schreibt
        ein einheitlich formatiertes Console-Hint und triggert defensiven
        Re-Sync des Schnitt-Workspaces. Returnt False -> Adapter MUSS
        sofort returnen, ohne den Worker-Pfad zu starten.
        """
        if self._ensure_combos_filled_from_project():
            return True
        self.window.console_text.append(
            f"[SCHNITT] {feature} braucht mind. 1 Audio + 1 Video. "
            "Importiere Material in MATERIAL & ANALYSE."
        )
        ws = getattr(self.window, "_schnitt_ws", None)
        if ws is not None:
            try:
                # I-1: refresh als defensiver Re-Sync — bei Empty-State ist es No-Op,
                # bei Loading->Empty wuerde es State zuruecksetzen falls Race.
                ws.refresh_state_from_db()
            except Exception as exc:
                logger.debug(
                    "B-294 ws.refresh_state_from_db (no-op-on-empty) failed: %s",
                    exc,
                )
        return False

    def _require_schnitt_action(self, feature: str) -> bool:
        binder = getattr(self.window, "_schnitt_action_binder", None)
        if binder is None:
            return self._guard_combos_or_notify(feature)
        if binder.refresh_current_project():
            return True
        reason = binder.block_reason()
        self.window.console_text.append(f"[SCHNITT] {feature} blockiert: {reason}")
        ws = getattr(self.window, "_schnitt_ws", None)
        if ws is not None:
            try:
                ws.refresh_state_from_db()
            except Exception as exc:
                logger.debug("schnitt refresh after blocked action failed: %s", exc)
        return False

    def _refresh_timeline_usage_marking(
        self, usage: dict | None = None, extra: str = "",
    ) -> None:
        """Fixplan 2026-07-07 Schritt 7c: Verwendungs-Markierung im
        MATERIAL-Pool nach JEDER Timeline-Aenderung (Add + Auto-Edit).

        usage=None -> aus der Timeline-DB berechnen (media_id -> Anzahl).
        Aktualisiert Tabelle (gruen/ausgegraut), Grid-Badges und das
        sichtbare Hinweis-Label.
        """
        try:
            if usage is None:
                from database import TimelineEntry, nullpool_session
                project_id = get_active_project_id()
                if project_id is None:
                    return
                usage = {}
                with nullpool_session() as session:
                    rows = (
                        session.query(TimelineEntry.media_id)
                        .filter_by(project_id=project_id, track="video")
                        .all()
                    )
                for (mid,) in rows:
                    if mid is not None:
                        usage[int(mid)] = usage.get(int(mid), 0) + 1

            vm = getattr(self.window, "video_pool_model", None)
            if vm is not None and hasattr(vm, "set_timeline_usage"):
                vm.set_timeline_usage(usage)
            grid = getattr(self.window, "video_grid", None)
            if grid is not None and hasattr(grid, "set_timeline_usage"):
                grid.set_timeline_usage(usage)

            media_ws = getattr(self.window, "_media_ws", None)
            if media_ws is not None and hasattr(media_ws, "set_timeline_usage_summary"):
                total = 0
                if vm is not None and hasattr(vm, "rowCount"):
                    try:
                        # Fix (Audit 2026-07-27): rowCount() ist beim
                        # paginierten Video-Pool auf die exponierten Zeilen
                        # gekappt -> "X von 100" statt "X von 375".
                        _total_fn = getattr(vm, "total_row_count", None)
                        total = _total_fn() if callable(_total_fn) else vm.rowCount()
                    except TypeError:
                        total = 0
                media_ws.set_timeline_usage_summary(len(usage), total, extra)
        except Exception as exc:
            logger.warning("Timeline-Usage-Markierung fehlgeschlagen: %s", exc)

    def _on_schnitt_auto_edit_request(self, profile) -> None:
        # B-294/R-14: kein silent return — wenn Combos leer, Auto-Fill aus DB.
        if not self._guard_combos_or_notify("Auto-Edit"):
            return
        self._auto_edit_to_beat()

    def _on_schnitt_regenerate_request(self, profile) -> None:
        if not self._guard_combos_or_notify("Re-Generate"):
            return
        self._generate_timeline_impl()

    @staticmethod
    def _coerce_media_id(value) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text.isdigit():
            return None
        return int(text)

    def _checked_ids_for_table(self, table) -> list[int]:
        model = table.model()
        getter = getattr(model, "get_checked_ids", None)
        if not callable(getter):
            return []
        ids: list[int] = []
        for value in getter() or []:
            media_id = self._coerce_media_id(value)
            if media_id is not None:
                ids.append(media_id)
        return ids

    def _selected_row_request(self, table, media_type: str) -> dict | None:
        model = table.model()
        indexes = table.selectionModel().selectedRows()
        if not indexes:
            return None
        row = indexes[0].row()
        media_id = self._coerce_media_id(model.index(row, 1).data())
        if media_id is None:
            return None
        title = model.index(row, 2).data() or f"{media_type} #{media_id}"
        return {"media_type": media_type, "media_id": media_id, "title": title}

    def _collect_timeline_add_requests(self) -> list[dict]:
        """Checkbox-Auswahl ist primaer; Row-Selection bleibt Fallback."""
        requests: list[dict] = []

        audio_ids = self._checked_ids_for_table(self.window.audio_pool_table)
        video_ids = self._checked_ids_for_table(self.window.video_pool_table)

        if audio_ids:
            if len(audio_ids) > 1:
                logger.info(
                    "Timeline-Add: %d Audio-Checkboxen gesetzt; nutze ersten Track als A1-Master.",
                    len(audio_ids),
                )
            requests.append({"media_type": "Audio", "media_id": audio_ids[0], "title": None})

        requests.extend(
            {"media_type": "Video", "media_id": media_id, "title": None}
            for media_id in video_ids
        )

        if requests:
            return requests

        audio_request = self._selected_row_request(self.window.audio_pool_table, "Audio")
        if audio_request is not None:
            return [audio_request]

        video_request = self._selected_row_request(self.window.video_pool_table, "Video")
        if video_request is not None:
            return [video_request]

        return []

    def _add_selected_to_timeline(self):
        """Fügt markierte Medien asynchron zur Timeline hinzu (Fix F-045/B-321)."""
        requests = self._collect_timeline_add_requests()
        if not requests:
            self.window.console_text.append("[Warnung] Keine Datei ausgewaehlt.")
            return

        project_id = get_active_project_id()
        if project_id is None:
            self.window.console_text.append("[Warnung] Kein aktives Projekt.")
            return

        # B-796: Projekt-Token beim Start festhalten. Die project_id allein
        # reicht nicht — sie kollidiert ueber Projekt-DBs hinweg. Ohne den
        # Abgleich unten landen die vorbereiteten Clips in der Timeline des
        # inzwischen gewechselten Projekts. Gleiches Muster wie B-714/B-795.
        from ui.controllers.schnitt_controller import _current_project_token
        _started_token = _current_project_token()

        def _project_changed() -> bool:
            if _started_token is None:
                return False  # fail-open, wie beim B-714-Guard
            _now = _current_project_token()
            return _now is not None and _now != _started_token

        # 2. DB-Abfrage in Hintergrund-Thread auslagern
        from PySide6.QtCore import QObject, Signal

        class AddClipsWorker(QObject):
            # Fixplan 2026-07-07 Schritt 7b: prepared clips + Budget-Info
            finished = Signal(list, dict)
            error = Signal(str)

            def __init__(self, project_id: int, requests: list[dict]):
                super().__init__()
                self._project_id = project_id
                self._requests = requests

            def run(self):
                try:
                    from database import nullpool_session, AudioTrack
                    from sqlalchemy import select  # B-090: column-select statt Blob-Voll-Load
                    from services.timeline_service import plan_video_timeline_add

                    prepared: list[dict] = []
                    audio_hint: int | None = None
                    with nullpool_session() as session:
                        for req in self._requests:
                            if req["media_type"] != "Audio":
                                continue
                            media_id = int(req["media_id"])
                            # B-090: column-select statt ORM-Voll-Laden (waveform_data/beatgrid joined); nutzt nur duration, title
                            obj = session.execute(
                                select(AudioTrack.duration, AudioTrack.title).where(AudioTrack.id == media_id)
                            ).first()
                            if obj is None:
                                raise ValueError(f"Audio #{media_id} nicht gefunden.")
                            duration = float(obj.duration or 30.0)
                            title = req.get("title") or obj.title or f"Audio #{media_id}"
                            prepared.append({
                                "media_type": "Audio",
                                "track_type": "audio",
                                "media_id": media_id,
                                "title": title,
                                "start_time": 0.0,
                                "duration": duration,
                            })
                            audio_hint = media_id

                    # Schritt 7b: Video-Uebergabe laeuft durch den zentralen
                    # Budget-Planer (Audio-Laenge = Limit, Duplikat-Schutz
                    # bei Bulk). Vorher: ungebremstes Append aller Markierten.
                    video_ids = [int(r["media_id"]) for r in self._requests
                                 if r["media_type"] != "Audio"]
                    plan = plan_video_timeline_add(
                        self._project_id, video_ids, audio_id_hint=audio_hint)
                    if plan["blocked_reason"] is None:
                        for clip in plan["accepted"]:
                            prepared.append({
                                "media_type": "Video",
                                "track_type": "video",
                                "media_id": clip["media_id"],
                                "title": clip["title"],
                                "start_time": clip["start_time"],
                                "duration": clip["duration"],
                            })
                    self.finished.emit(prepared, plan)
                except Exception as e: self.error.emit(str(e))

        worker = AddClipsWorker(project_id, requests)

        def _notify(text: str) -> None:
            """Konsole + Statusbar — Kappen darf nie stumm passieren (7b)."""
            self.window.console_text.append(text)
            try:
                self.window.statusBar().showMessage(text.replace("[Timeline] ", ""), 10000)
            except Exception:
                pass

        def _on_done(clips, plan=None):
            # B-796: Ergebnis eines fremden Projekts nicht anwenden — weder
            # Clips pushen noch Banner/Workspace umschalten.
            if _project_changed():
                logger.warning(
                    "B-796: Timeline-Add verworfen — Projekt gewechselt "
                    "(Start-Projekt %s).", project_id,
                )
                return
            plan = plan or {}
            if plan.get("blocked_reason"):
                _notify(f"[Timeline] Nicht hinzugefuegt: {plan['blocked_reason']}")
                self._refresh_timeline_usage_marking(extra=plan["blocked_reason"])
                return
            if not clips:
                if plan.get("skipped_duplicate") or plan.get("skipped_budget"):
                    _notify(
                        "[Timeline] Nichts hinzugefuegt: "
                        f"{len(plan.get('skipped_duplicate', []))} bereits in der "
                        f"Timeline, {len(plan.get('skipped_budget', []))} ueber der "
                        "Audio-Laenge. Tipp: Auto-Edit schneidet beat-genau auf "
                        "die Audio-Laenge."
                    )
                else:
                    self.window.console_text.append("[Warnung] Keine Timeline-Clips vorbereitet.")
                return
            from ui.undo_commands import AddClipCommand
            # Schritt 7b: Bulk-Add als EIN Undo-Schritt
            undo_stack = self.window.timeline_view.undo_stack
            use_macro = len(clips) > 1
            if use_macro:
                undo_stack.beginMacro(f"{len(clips)} Medien zur Timeline")
            try:
                for clip in clips:
                    cmd = AddClipCommand(
                        self.window.timeline_view,
                        project_id,
                        clip["track_type"],
                        clip["media_id"],
                        clip["title"],
                        clip["start_time"],
                        clip["duration"],
                    )
                    undo_stack.push(cmd)
            finally:
                if use_macro:
                    undo_stack.endMacro()
            self.window._mark_dirty()

            n_dup = len(plan.get("skipped_duplicate", []))
            n_budget = len(plan.get("skipped_budget", []))
            budget = plan.get("budget")
            if len(clips) == 1 and not (n_dup or n_budget):
                clip = clips[0]
                _notify(f"[Timeline] {clip['media_type']} '{clip['title']}' hinzugefuegt.")
            else:
                msg = f"[Timeline] {len(clips)} Medien hinzugefuegt."
                extras = []
                if n_budget:
                    extras.append(
                        f"{n_budget} nicht uebergeben — Audio-Laenge "
                        f"({budget:.0f}s) erreicht" if budget is not None
                        else f"{n_budget} nicht uebergeben (Laengen-Limit)")
                if n_dup:
                    extras.append(f"{n_dup} uebersprungen (bereits in Timeline)")
                if extras:
                    msg += " " + "; ".join(extras) + ". Tipp: Auto-Edit waehlt Clips beat-genau."
                _notify(msg)

            # Schritt 7c: Markierung + sichtbares Label nach JEDEM Add —
            # nicht nur nach Auto-Edit (User-Vorgabe V3).
            _label_extra = ""
            if n_budget and budget is not None:
                _label_extra = (
                    f"{n_budget} Clips nicht uebergeben (Audio-Laenge "
                    f"{budget:.0f}s erreicht)."
                )
            elif n_dup:
                _label_extra = f"{n_dup} Clips waren bereits in der Timeline."
            self._refresh_timeline_usage_marking(extra=_label_extra)
            self.window.nav_bar.set_workspace(1)

        GlobalTaskManager.instance().start_task(
            name="Clips zur Timeline", worker=worker, on_finish=_on_done
        )
