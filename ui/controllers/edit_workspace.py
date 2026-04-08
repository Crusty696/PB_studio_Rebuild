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
        cuts = calculate_cut_points(audio_id, video_id, settings, total_dur)
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

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        audio_id = self.window.audio_combo.currentData()
        if audio_id is None:
            self.window.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        video_ids = []
        for _row in range(self.window.video_pool_table.rowCount()):
            _id_item = self.window.video_pool_table.item(_row, 1)
            if _id_item:
                try:
                    video_ids.append(int(_id_item.text()))
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
                ).filter_by(project_id=get_active_project_id()).all()
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
            QTimer.singleShot(2000, lambda: self.window.btn_learn_ai.setStyleSheet("background-color: #d4a44a; color: #0a0d12; font-weight: 800; font-size: 10px; border-radius: 3px;"))
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
        media_type = None
        media_id = None
        title = None
        audio_row = self.window.audio_pool_table.currentRow()
        if audio_row >= 0:
            id_item = self.window.audio_pool_table.item(audio_row, 1)
            title_item = self.window.audio_pool_table.item(audio_row, 2)
            if id_item and id_item.text().isdigit():
                media_type = "Audio"
                media_id = int(id_item.text())
                title = title_item.text() if title_item else f"Audio #{media_id}"
        if media_id is None:
            video_row = self.window.video_pool_table.currentRow()
            if video_row >= 0:
                id_item = self.window.video_pool_table.item(video_row, 1)
                title_item = self.window.video_pool_table.item(video_row, 2)
                if id_item and id_item.text().isdigit():
                    media_type = "Video"
                    media_id = int(id_item.text())
                    title = title_item.text() if title_item else f"Video #{media_id}"
        if media_id is None:
            self.window.console_text.append("[Warnung] Keine Datei ausgewaehlt.")
            return

        track_type = "audio" if media_type == "Audio" else "video"
        with DBSession(engine) as session:
            existing = session.query(TimelineEntry).filter_by(project_id=get_active_project_id(), track=track_type).order_by(TimelineEntry.start_time.desc()).first()
            start_time = existing.end_time if existing and existing.end_time else 0.0
            if track_type == "audio":
                obj = session.get(AudioTrack, media_id)
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.get(VideoClip, media_id)
                duration = obj.duration if obj and obj.duration else 10.0

        from ui.undo_commands import AddClipCommand
        cmd = AddClipCommand(self.window.timeline_view, get_active_project_id(), track_type, media_id, title, start_time, duration)
        self.window.timeline_view.undo_stack.push(cmd)
        self.window._mark_dirty()
        self.window.console_text.append(f"[Timeline] {media_type} '{title}' hinzugefuegt.")
        self.window.nav_bar.set_workspace(1)
