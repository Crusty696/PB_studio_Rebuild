"""Edit-Workspace Mixin fuer PBWindow."""

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QDoubleSpinBox,
    QComboBox, QPushButton, QDialog, QTreeWidgetItem,
)
from PySide6.QtCore import Qt, QTimer

from database import engine, AudioTrack, VideoClip, TimelineEntry, get_active_project_id
from sqlalchemy.orm import Session as DBSession

from services.task_manager import GlobalTaskManager
from services.pacing_service import (
    PacingSettings, calculate_cut_points, CutPoint, auto_edit_to_beats,
    AdvancedPacingSettings, generate_keyframe_strings_for_project,
)
from services.timeline_service import TimelineService, PB_NS
from workers import AutoEditWorker


# task_manager Proxy — gleiche Logik wie in main.py
class _TaskManagerProxy:
    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)

task_manager = _TaskManagerProxy()


class EditWorkspaceMixin:
    """Edit workspace methods for PBWindow."""

    def _on_video_combo_changed(self, index: int):
        video_id = self.video_combo.currentData()
        if video_id is None:
            self.video_preview.setText("Keine Vorschau")
            return
        with DBSession(engine) as session:
            clip = session.get(VideoClip, video_id)
            if clip and clip.file_path:
                dur = clip.duration if clip.duration else 0.0
                self.video_preview.load_video(clip.file_path, dur)

    def _toggle_preview_play(self):
        self.video_preview.toggle_play()

    def _on_preview_position_changed(self, current: float, total: float):
        """Update the time label in the transport bar on every frame advance."""
        def _fmt(sec: float) -> str:
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"
        self.preview_time_label.setText(f"{_fmt(current)} / {_fmt(total)}")

    def _on_preview_state_changed(self, is_playing: bool):
        """Flip play button icon to reflect current playback state."""
        self.btn_preview_play.setText("\u23F8" if is_playing else "\u25B6")

    def _on_audio_combo_changed(self, index: int):
        """Audio-Track gewechselt: Pacing-Kurven-Dauer aktualisieren."""
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            return
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if track and track.duration:
                self.pacing_curve.set_duration(track.duration)
                self.console_text.append(
                    f"[Edit] Audio gewechselt: {track.title or 'Track'} "
                    f"({track.duration:.1f}s) — Pacing-Kurve aktualisiert."
                )

    def _generate_timeline(self):
        audio_id = self.audio_combo.currentData()
        video_id = self.video_combo.currentData()

        # Collect manual density curve from pacing widget
        densities = self.pacing_curve.get_all_densities()

        # Map cut_rate_combo to tempo for legacy PacingSettings
        cut_rate_map = {0: 90, 1: 70, 2: 50, 3: 30, 4: 10}
        tempo_val = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 50)
        reactivity = self.energy_reactivity_spin.value()

        settings = PacingSettings(
            tempo=tempo_val,
            energy=reactivity,
            cut_density=reactivity,
            vibe=self.vibe_input.text(),
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

        # Update pacing curve duration
        self.pacing_curve.set_duration(total_dur)

        cuts = calculate_cut_points(audio_id, video_id, settings, total_dur)

        # Gold Beat-Marker: Alle Beat-basierten Cuts als goldene Linien anzeigen
        beat_times = [cp.time for cp in cuts if cp.source == "beat"]
        self.timeline_view.set_beat_markers(beat_times)

        self.timeline_view.load_from_db()
        self.timeline_view.set_cut_points(cuts, total_dur)

        beat_cuts = sum(1 for c in cuts if c.source == "beat")
        scene_cuts = sum(1 for c in cuts if c.source == "scene")
        energy_cuts = sum(1 for c in cuts if c.source == "energy")
        drum_cuts = sum(1 for c in cuts if c.source == "drum")
        self.cut_info_label.setText(
            f"{len(cuts)} Cuts | Beat:{beat_cuts} Szene:{scene_cuts} "
            f"Energie:{energy_cuts} Drum:{drum_cuts} | {total_dur:.0f}s"
        )
        self.console_text.append(
            f"[Pacing] {len(cuts)} Cuts generiert (Manual Curve aktiv)"
        )

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        # Clip-IDs aus der bereits geladenen Video-Pool-Tabelle lesen (kein Main-Thread DB-Block)
        video_ids = []
        for _row in range(self.video_pool_table.rowCount()):
            _id_item = self.video_pool_table.item(_row, 1)
            if _id_item:
                try:
                    video_ids.append(int(_id_item.text()))
                except ValueError:
                    pass

        if not video_ids:
            self.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        # Phase 3: DJ-Regler auslesen
        cut_rate_map = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}
        base_cut_rate = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 4)

        breakdown_map = {0: "halve", 1: "force16", 2: "none"}
        breakdown = breakdown_map.get(self.breakdown_combo.currentIndex(), "halve")

        # Anker aus UI sammeln
        anchors = self._collect_anchors_from_ui()

        settings = AdvancedPacingSettings(
            base_cut_rate=base_cut_rate,
            energy_reactivity=self.energy_reactivity_spin.value(),
            breakdown_behavior=breakdown,
            vibe=self.vibe_input.text(),
            manual_density_curve=self.pacing_curve.get_all_densities(),
            anchors=anchors,
        )

        self.console_text.append(
            f"[Auto-Edit] Phase 3 DJ-Pacing starte "
            f"(Rate={base_cut_rate} Beats, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}, {len(video_ids)} Clips, "
            f"{len(anchors)} Anker)..."
        )
        self.btn_auto_edit.setEnabled(False)
        self.btn_auto_edit.setText("laeuft...")

        # Task erstellen und Worker ueber _start_worker_thread starten
        tm = GlobalTaskManager.instance()
        task = tm.create_task(
            "Auto-Edit (Phase 3)",
            f"DJ-Pacing: {base_cut_rate}-Beat, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}"
        )
        worker = AutoEditWorker(audio_id, video_ids, settings)
        worker.task_id = task.task_id
        self._start_worker_thread(
            worker,
            on_finish=lambda segs, cps: self._on_auto_edit_finished(segs, cps, task.task_id),
            on_error=lambda err: self._on_auto_edit_error(err, task.task_id),
        )

    def _on_auto_edit_finished(self, segments: list, cut_points: list, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")

        if not segments:
            # Could be error-path fallback OR legitimate empty result (no beats)
            if not cut_points:
                return  # Error-path: _on_auto_edit_error already handled
            self.console_text.append("[Auto-Edit] Keine Segmente erzeugt (kein Audio/Beats?).")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        # 1. SQLite TimelineEntries aktualisieren (via Service — atomar)
        from services.timeline_service import apply_auto_edit_segments
        apply_auto_edit_segments(segments, get_active_project_id())

        # 2. OTIO Timeline generieren
        self._build_otio_timeline(segments)

        # 3. UI aktualisieren
        self.timeline_view.load_from_db()

        # 4. CutPoints visualisieren
        if cut_points:
            total_dur = segments[-1]["end"] if segments else 60.0
            cps = [CutPoint(
                time=cp["time"], source=cp["source"], strength=cp["strength"]
            ) for cp in cut_points]
            # Gold Beat-Marker für Beat-Cuts
            beat_times = [cp["time"] for cp in cut_points if cp["source"] == "beat"]
            self.timeline_view.set_beat_markers(beat_times)
            self.timeline_view.set_cut_points(cps, total_dur)

            anchor_cuts = sum(1 for cp in cut_points if cp["source"] == "anchor")
            beat_cuts = sum(1 for cp in cut_points if cp["source"] == "beat")
            self.cut_info_label.setText(
                f"{len(cut_points)} Cuts | Beat:{beat_cuts} Anker:{anchor_cuts} | "
                f"{total_dur:.0f}s | {len(segments)} Segmente"
            )

        self.console_text.append(
            f"[Auto-Edit] Phase 3 fertig: {len(segments)} Segmente, "
            f"OTIO Timeline generiert."
        )
        task_manager.finish_task(task_id, "finished", f"{len(segments)} Segmente")

    def _build_otio_timeline(self, segments: list):
        """Baut eine OTIO-Timeline aus den Auto-Edit Segmenten."""
        audio_id = self.audio_combo.currentData()
        tls = TimelineService(fps=30.0)
        tls.create_timeline("PB Studio Auto-Edit")

        # Audio-Track hinzufuegen
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

        # Video-Clips hinzufuegen
        video_track = tls.get_video_track()
        for seg in segments:
            source_duration = seg.get("source_end", seg["end"]) - seg.get("source_start", seg["start"])
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

        # Anker als OTIO Marker speichern
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

        # Speichern
        self._otio_timeline_service = tls
        otio_path = tls.save_otio("exports/auto_edit_phase3.otio")
        self.console_text.append(f"[OTIO] Timeline gespeichert: {otio_path}")

    def _on_auto_edit_error(self, error_msg: str, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")
        self.console_text.append(f"[Auto-Edit Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    def _collect_anchors_from_ui(self) -> list[dict]:
        """Sammelt alle Anker aus der Anchor-Liste im Inspector."""
        anchors = []
        for i in range(self.anchor_list.topLevelItemCount()):
            item = self.anchor_list.topLevelItem(i)
            time_text = item.text(0)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole) or ""
            try:
                # Parse "MM:SS.ss" or plain seconds
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
        """Oeffnet einen Dialog zum Hinzufuegen eines neuen Audio-Ankers."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Anker hinzufuegen")
        dialog.setFixedSize(320, 180)
        dialog.setStyleSheet("background-color: #161c26; color: #e8e6e3;")
        layout = QVBoxLayout(dialog)

        # Zeitpunkt
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

        # Video/Szene Auswahl
        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Video/Szene:"))
        scene_combo = QComboBox()
        scene_combo.addItem("-- Szene waehlen --", "")
        # Alle Szenen aus der DB laden (joinedload verhindert N+1)
        from sqlalchemy.orm import joinedload
        with DBSession(engine) as session:
            clips = session.query(VideoClip).options(
                joinedload(VideoClip.scenes)
            ).filter_by(project_id=get_active_project_id()).all()
            for clip in clips:
                clip_name = Path(clip.file_path).stem[:20]
                for scene in clip.scenes:
                    label = (
                        f"{clip_name} | Szene {scene.id} "
                        f"({scene.start_time:.1f}-{scene.end_time:.1f}s)"
                    )
                    scene_combo.addItem(label, str(scene.id))
                # Falls keine Szenen: ganzen Clip anbieten
                if not clip.scenes:
                    scene_combo.addItem(f"{clip_name} (komplett)", f"clip_{clip.id}")
        scene_row.addWidget(scene_combo)
        layout.addLayout(scene_row)

        # OK/Cancel
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

            # Zur Anchor-Liste hinzufuegen
            minutes = int(time_sec // 60)
            secs = time_sec % 60
            time_str = f"{minutes}:{secs:05.2f}"

            item = QTreeWidgetItem([time_str, scene_label[:30]])
            item.setData(0, Qt.ItemDataRole.UserRole, scene_id)
            self.anchor_list.addTopLevelItem(item)

            self.console_text.append(
                f"[Anchor] Anker bei {time_str} -> {scene_label}"
            )

    def _remove_selected_anchor(self):
        """Entfernt den ausgewaehlten Anker aus der Liste."""
        selected = self.anchor_list.currentItem()
        if selected:
            idx = self.anchor_list.indexOfTopLevelItem(selected)
            self.anchor_list.takeTopLevelItem(idx)
            self.console_text.append("[Anchor] Anker entfernt.")

    def _sync_anchors(self):
        """Anker synchronisieren — richtet Video-Clips an Audio-Ankern aus."""
        synced = self.timeline_view.sync_anchors()
        if synced:
            self.timeline_view.load_from_db()
            self.console_text.append(
                "[Anchor] Anker synchronisiert — Video-Clips an Audio-Ankern ausgerichtet."
            )
        else:
            self.console_text.append(
                "[Anchor] Keine Anker gefunden. Setze Anker auf Audio- und Video-Clips "
                "(Rechtsklick oder Taste M), dann klicke erneut."
            )

    def _learn_anchor_as_ai_rule(self):
        """Speichert den ausgewaehlten Anker als KI-Lernregel fuer den Auto-Edit."""
        selected = self.anchor_list.currentItem()
        if not selected:
            self.console_text.append(
                "[KI-Gedaechtnis] Kein Anker ausgewaehlt. Bitte zuerst einen Anker in der Liste auswaehlen."
            )
            return

        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append(
                "[KI-Gedaechtnis] Kein Audio-Track ausgewaehlt. Bitte Audio-Combo setzen."
            )
            return

        time_text = selected.text(0)
        scene_id_raw = selected.data(0, Qt.ItemDataRole.UserRole)

        # Zeit parsen (Format "MM:SS.ss" oder Dezimal-Sekunden)
        try:
            if ":" in str(time_text):
                parts = str(time_text).split(":")
                anchor_time = int(parts[0]) * 60 + float(parts[1])
            else:
                anchor_time = float(time_text)
        except (ValueError, IndexError):
            self.console_text.append("[KI-Gedaechtnis] Fehler beim Parsen der Anker-Zeit.")
            return

        try:
            scene_int = int(scene_id_raw) if scene_id_raw else None
        except (ValueError, TypeError):
            scene_int = None

        label = f"Anker@{time_text}"

        from services.pacing_service import learn_from_anchor
        success = learn_from_anchor(audio_id, anchor_time, scene_int, label)

        if success:
            self.console_text.append(
                f"[KI-Gedaechtnis] Regel gelernt: {time_text}"
                + (f" | Szene #{scene_int}" if scene_int else "")
                + " — Wird beim naechsten Auto-Edit beruecksichtigt."
            )
            # Visuelles Feedback: kurz gruen aufleuchten
            self.btn_learn_ai.setStyleSheet(
                "background-color: #4ade80; color: #0a0d12; font-weight: 800; "
                "font-size: 10px; border-radius: 3px; letter-spacing: 1px;"
            )
            QTimer.singleShot(2000, lambda: self.btn_learn_ai.setStyleSheet(
                "background-color: #d4a44a; color: #0a0d12; font-weight: 800; "
                "font-size: 10px; border-radius: 3px; letter-spacing: 1px;"
            ))
        else:
            self.console_text.append("[KI-Gedaechtnis] Fehler beim Speichern der Regel.")

    def _rl_feedback_positive(self):
        """RL Feedback: User bestätigt aktuelle Pacing-Entscheidung (Thumbs Up)."""
        self._save_rl_feedback("positive")

    def _rl_feedback_negative(self):
        """RL Feedback: User lehnt aktuelle Pacing-Entscheidung ab (Thumbs Down)."""
        self._save_rl_feedback("negative")

    def _save_rl_feedback(self, sentiment: str):
        """Speichert RL-Feedback via pacing_service."""
        from services.pacing_service import record_rl_feedback

        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append(
                f"[RL-Feedback] {sentiment} - Kein Audio-Track gewaehlt, "
                "bitte Audio-Combo im Edit-Workspace setzen."
            )
            return

        success = record_rl_feedback(audio_id, sentiment, get_active_project_id())
        if success:
            emoji = "\U0001f44d" if sentiment == "positive" else "\U0001f44e"
            self.console_text.append(f"[RL-Feedback] {emoji} {sentiment.title()} gespeichert")
            self.statusBar().showMessage(f"RL-Feedback: {sentiment.title()} gespeichert", 3000)
        else:
            self.console_text.append(f"[RL-Feedback] Fehler beim Speichern")

    def _apply_style_preset(self, index: int):
        """Wendet einen Style-Preset auf die Pacing-Einstellungen an."""
        from database import engine, StylePreset
        from sqlalchemy.orm import Session as DBSession
        preset_name = self._edit_ws.style_preset_combo.currentText()
        if not preset_name:
            return
        try:
            with DBSession(engine) as session:
                preset = session.query(StylePreset).filter_by(name=preset_name).first()
                if not preset:
                    return
                # Preset-Werte in UI-Widgets schreiben
                cut_rate_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}
                closest_beat = min(cut_rate_map.keys(), key=lambda x: abs(x - preset.cut_rate))
                self._edit_ws.cut_rate_combo.setCurrentIndex(cut_rate_map.get(closest_beat, 2))
                # Energy Reactivity (0-100 Slider)
                self._edit_ws.energy_reactivity_slider.setValue(int(preset.energy_reactivity * 100))
                # Breakdown Behavior
                breakdown_map = {"halve": 0, "16beat": 1, "none": 2}
                self._edit_ws.breakdown_combo.setCurrentIndex(breakdown_map.get(preset.breakdown_behavior, 0))
                self.console_text.append(
                    f"[Style-Preset] '{preset_name}' angewendet: "
                    f"Cut-Rate={preset.cut_rate}, Energy={preset.energy_reactivity}, "
                    f"Breakdown={preset.breakdown_behavior}"
                )
                self.statusBar().showMessage(f"Style-Preset '{preset_name}' angewendet", 3000)
        except Exception as e:
            self.console_text.append(f"[Style-Preset] Fehler: {e}")

    def _show_keyframe_strings(self):
        """Phase 3: Generiert und zeigt die Keyframe-Strings aller Video-Clips."""
        try:
            kf_string = generate_keyframe_strings_for_project(project_id=get_active_project_id())
            self.keyframe_text.setPlainText(kf_string)
            self.console_text.append("[Pacing] Keyframe-Strings generiert.")
        except Exception as e:
            self.keyframe_text.setPlainText(f"Fehler: {e}")
            self.console_text.append(f"[Pacing-Fehler] Keyframe-Strings: {e}")

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.console_text.append(
            f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s"
        )

    def _add_selected_to_timeline(self):
        # Primaer: Audio-Pool pruefen
        media_type = None
        media_id = None
        title = None

        audio_row = self.audio_pool_table.currentRow()
        if audio_row >= 0:
            id_item = self.audio_pool_table.item(audio_row, 1)
            title_item = self.audio_pool_table.item(audio_row, 2)
            if id_item and id_item.text().isdigit():
                media_type = "Audio"
                media_id = int(id_item.text())
                title = title_item.text() if title_item else f"Audio #{media_id}"

        # Fallback: Video-Pool pruefen
        if media_id is None:
            video_row = self.video_pool_table.currentRow()
            if video_row >= 0:
                id_item = self.video_pool_table.item(video_row, 1)
                title_item = self.video_pool_table.item(video_row, 2)
                if id_item and id_item.text().isdigit():
                    media_type = "Video"
                    media_id = int(id_item.text())
                    title = title_item.text() if title_item else f"Video #{media_id}"

        if media_id is None:
            self.console_text.append("[Warnung] Keine Datei in Audio- oder Video-Pool ausgewaehlt.")
            return

        track_type = "audio" if media_type == "Audio" else "video"

        with DBSession(engine) as session:
            existing = (
                session.query(TimelineEntry)
                .filter_by(project_id=get_active_project_id(), track=track_type)
                .order_by(TimelineEntry.start_time.desc())
                .first()
            )
            start_time = 0.0
            if existing and existing.end_time:
                start_time = existing.end_time

            if track_type == "audio":
                obj = session.get(AudioTrack, media_id)
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.get(VideoClip, media_id)
                duration = obj.duration if obj and obj.duration else 10.0

            entry = TimelineEntry(
                project_id=get_active_project_id(),
                track=track_type,
                media_id=media_id,
                start_time=round(start_time, 3),
                end_time=round(start_time + duration, 3),
                lane=0,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        self.timeline_view.add_clip(
            entry_id=entry_id,
            media_id=media_id,
            track_type=track_type,
            title=title,
            start_time=start_time,
            duration=duration,
        )

        self.console_text.append(
            f"[Timeline] {media_type} '{title}' hinzugefuegt bei {start_time:.1f}s "
            f"(Dauer: {duration:.1f}s)"
        )

        # Automatisch zum EDIT Workspace wechseln
        self.nav_bar.set_workspace(1)
