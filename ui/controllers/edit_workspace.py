"""EditWorkspaceController — Refactored from EditWorkspaceMixin."""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QDoubleSpinBox,
    QComboBox, QPushButton, QDialog, QTreeWidgetItem,
)
from PySide6.QtCore import Qt, QTimer
from database import engine, AudioTrack, VideoClip, TimelineEntry, get_active_project_id
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
            clip = session.get(VideoClip, video_id)
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
        if audio_id is None:
            return
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if track and track.duration:
                self.window.pacing_curve.set_duration(track.duration)
                if hasattr(self.window, "console_text"):
                    self.window.console_text.append(
                        f"[Edit] Audio gewechselt: {track.title or 'Track'} "
                        f"({track.duration:.1f}s) — Pacing-Kurve aktualisiert."
                    )

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
        # Alten Thread NICHT mehr blocking abwarten — Qt's parented-thread-
        # Cleanup (parent=self.window) macht das beim Window-Close.

        class _CutsWorker(QObject):
            done = Signal(list, float, int)
            failed = Signal(str, int)

            def __init__(self, audio_id, video_id, settings, total_dur, seq):
                super().__init__()
                self._args = (audio_id, video_id, settings, total_dur)
                self._seq = seq

            def run(self):
                try:
                    cuts = calculate_cut_points(*self._args)
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
        self._cuts_thread.start()

    def _on_cuts_done(self, cuts: list, total_dur: float, seq: int = 0):
        # B-172: stale-result Drop wenn neuerer Klick schon in Flight.
        if seq and seq != getattr(self, "_gen_seq", seq):
            logger.debug("_on_cuts_done: stale seq %d (current %d), ignored.",
                         seq, self._gen_seq)
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

    def _on_cuts_failed(self, err: str, seq: int = 0):
        # B-172: stale-Fail-Drop
        if seq and seq != getattr(self, "_gen_seq", seq):
            return
        logger.warning("calculate_cut_points failed: %s", err)
        self.window.console_text.append(f"[Pacing-Fehler] {err}")

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        audio_id = self.window.audio_combo.currentData()
        if audio_id is None:
            self.window.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        video_ids = []
        # P9-C: direkt das Source-Model nehmen — der Proxy paginiert und
        # wuerde sonst nur die aktuell sichtbaren 16 Zeilen liefern.
        v_model = getattr(self.window, "video_pool_model", None) or self.window.video_pool_table.model()
        if v_model:
            for _row in range(v_model.rowCount()):
                _id_val = v_model.index(_row, 1).data()
                if _id_val:
                    try:
                        video_ids.append(int(_id_val))
                    except ValueError as exc:
                        logger.warning("_start_auto_edit: failed to parse video clip ID: %s", exc)

        if not video_ids:
            self.window.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        cut_rate_map = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}
        base_cut_rate = cut_rate_map.get(self.window.cut_rate_combo.currentIndex(), 4)
        breakdown_map = {0: "halve", 1: "force16", 2: "none"}
        breakdown = breakdown_map.get(self.window.breakdown_combo.currentIndex(), "halve")
        anchors = self._collect_anchors_from_ui()

        settings = AdvancedPacingSettings(
            base_cut_rate=base_cut_rate,
            energy_reactivity=self.window.energy_reactivity_spin.value(),
            breakdown_behavior=breakdown,
            vibe=self.window.vibe_input.text(),
            manual_density_curve=self.window.pacing_curve.get_all_densities(),
            anchors=anchors,
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

        tm = GlobalTaskManager.instance()
        task = tm.create_task(
            "Auto-Edit (Phase 3)",
            f"DJ-Pacing: {base_cut_rate}-Beat, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}"
        )
        worker = AutoEditWorker(audio_id, video_ids, settings)
        worker.task_id = task.task_id
        self.window.worker_dispatcher._start_worker_thread(
            worker,
            on_finish=lambda segs, cps: self._on_auto_edit_finished(segs, cps, task.task_id),
            on_error=lambda err: self._on_auto_edit_error(err, task.task_id),
        )

    def _on_auto_edit_finished(self, segments: list, cut_points: list, task_id: str):
        self.window.btn_auto_edit.setEnabled(True)
        self.window.btn_auto_edit.setText("Auto-Edit")

        if not segments:
            if not cut_points:
                return
            self.window.console_text.append("[Auto-Edit] Keine Segmente erzeugt (kein Audio/Beats?).")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        from ui.undo_commands import ApplyAutoEditCommand
        cmd = ApplyAutoEditCommand(
            timeline=self.window.timeline_view,
            project_id=get_active_project_id(),
            new_segments=segments,
        )
        self.window.timeline_view.undo_stack.push(cmd)

        try:
            self._build_otio_timeline(segments)
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

    def _build_otio_timeline(self, segments: list):
        audio_id = self.window.audio_combo.currentData()
        tls = TimelineService(fps=30.0)
        tls.create_timeline("PB Studio Auto-Edit")

        if audio_id is not None:
            with DBSession(engine) as session:
                track = session.get(AudioTrack, audio_id)
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
        time_row.addWidget(time_spin)
        layout.addLayout(time_row)

        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Video/Szene:"))
        scene_combo = QComboBox()
        scene_combo.addItem("-- Szene waehlen --", "")
        from sqlalchemy.orm import joinedload
        try:
            with DBSession(engine) as session:
                clips = session.query(VideoClip).options(
                    joinedload(VideoClip.scenes)
                ).filter(
                    VideoClip.project_id == get_active_project_id(),
                    VideoClip.deleted_at.is_(None)
                ).all()
                for clip in clips:
                    clip_name = Path(clip.file_path).stem[:20]
                    for scene in clip.scenes:
                        label = f"{clip_name} | Szene {scene.id} ({scene.start_time:.1f}-{scene.end_time:.1f}s)"
                        scene_combo.addItem(label, str(scene.id))
                    if not clip.scenes:
                        scene_combo.addItem(f"{clip_name} (komplett)", f"clip_{clip.id}")
        except Exception as exc:
            logger.warning("_add_anchor_dialog: DB error loading scenes: %s", exc)
        scene_row.addWidget(scene_combo)
        layout.addLayout(scene_row)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Hinzufuegen")
        btn_ok.setObjectName("btn_accent")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("Abbrechen")
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

    def _sync_anchors(self):
        synced = self.window.timeline_view.sync_anchors()
        if synced:
            self.window.timeline_view.load_from_db()
            self.window.console_text.append("[Anchor] Anker synchronisiert — Video-Clips an Audio-Ankern ausgerichtet.")
        else:
            self.window.console_text.append("[Anchor] Keine Anker gefunden. Setze Anker auf Audio- und Video-Clips (Rechtsklick oder Taste M), dann klicke erneut.")

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
        from database import engine, StylePreset
        from sqlalchemy.orm import Session as DBSession
        preset_name = self.window._edit_ws.style_preset_combo.currentText()
        if not preset_name:
            return
        try:
            with DBSession(engine) as session:
                preset = session.query(StylePreset).filter_by(name=preset_name).first()
                if not preset:
                    return
                cut_rate_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}
                closest_beat = min(cut_rate_map.keys(), key=lambda x: abs(x - preset.cut_rate))
                self.window._edit_ws.cut_rate_combo.setCurrentIndex(cut_rate_map.get(closest_beat, 2))
                self.window._edit_ws.energy_reactivity_slider.setValue(int(preset.energy_reactivity * 100))
                breakdown_map = {"halve": 0, "16beat": 1, "none": 2}
                self.window._edit_ws.breakdown_combo.setCurrentIndex(breakdown_map.get(preset.breakdown_behavior, 0))
                self.window.console_text.append(f"[Style-Preset] '{preset_name}' angewendet.")
                self.window.statusBar().showMessage(f"Style-Preset '{preset_name}' angewendet", 3000)
        except Exception as e:
            self.window.console_text.append(f"[Style-Preset] Fehler: {e}")

    def _show_keyframe_strings(self):
        try:
            kf_string = generate_keyframe_strings_for_project(project_id=get_active_project_id())
            self.window.keyframe_text.setPlainText(kf_string)
            self.window.console_text.append("[Pacing] Keyframe-Strings generiert.")
        except Exception as e:
            self.window.keyframe_text.setPlainText(f"Fehler: {e}")
            self.window.console_text.append(f"[Pacing-Fehler] Keyframe-Strings: {e}")

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.window._mark_dirty()
        self.window.console_text.append(f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s")

    def _add_selected_to_timeline(self):
        """Fügt selektiertes Medium asynchron zur Timeline hinzu (Fix F-045)."""
        media_type = None
        media_id = None
        title = None
        
        # 1. Auswahl-Ermittlung (bleibt im UI-Thread)
        a_view = self.window.audio_pool_table
        a_model = a_view.model()
        a_indexes = a_view.selectionModel().selectedRows()
        if a_indexes:
            row = a_indexes[0].row()
            mid = a_model.index(row, 1).data()
            if mid and str(mid).isdigit():
                media_type = "Audio"; media_id = int(mid)
                title = a_model.index(row, 2).data() or f"Audio #{media_id}"

        if media_id is None:
            v_view = self.window.video_pool_table
            v_model = v_view.model()
            v_indexes = v_view.selectionModel().selectedRows()
            if v_indexes:
                row = v_indexes[0].row()
                mid = v_model.index(row, 1).data()
                if mid and str(mid).isdigit():
                    media_type = "Video"; media_id = int(mid)
                    title = v_model.index(row, 2).data() or f"Video #{media_id}"

        if media_id is None:
            self.window.console_text.append("[Warnung] Keine Datei ausgewaehlt.")
            return

        track_type = "audio" if media_type == "Audio" else "video"
        
        # 2. DB-Abfrage in Hintergrund-Thread auslagern
        from PySide6.QtCore import QObject, Signal
        class AddClipWorker(QObject):
            finished = Signal(float, float) # start_time, duration
            error = Signal(str)
            def run(self):
                try:
                    from database import nullpool_session, TimelineEntry, AudioTrack, VideoClip, get_active_project_id
                    with nullpool_session() as session:
                        existing = session.query(TimelineEntry).filter_by(
                            project_id=get_active_project_id(), track=track_type
                        ).order_by(TimelineEntry.start_time.desc()).first()
                        st = existing.end_time if existing and existing.end_time else 0.0
                        if track_type == "audio":
                            obj = session.get(AudioTrack, media_id)
                            dur = obj.duration if obj and obj.duration else 30.0
                        else:
                            obj = session.get(VideoClip, media_id)
                            dur = obj.duration if obj and obj.duration else 10.0
                        self.finished.emit(st, dur)
                except Exception as e: self.error.emit(str(e))

        worker = AddClipWorker()
        def _on_done(start_time, duration):
            from ui.undo_commands import AddClipCommand
            cmd = AddClipCommand(self.window.timeline_view, get_active_project_id(), 
                               track_type, media_id, title, start_time, duration)
            self.window.timeline_view.undo_stack.push(cmd)
            self.window._mark_dirty()
            self.window.console_text.append(f"[Timeline] {media_type} '{title}' hinzugefuegt.")
            self.window.nav_bar.set_workspace(1)

        GlobalTaskManager.instance().start_task(
            name="Clip zur Timeline", worker=worker, on_finish=_on_done
        )
