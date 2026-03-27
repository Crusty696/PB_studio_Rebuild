"""Audio-Analyse Mixin fuer PBWindow."""

from services.task_manager import GlobalTaskManager

from workers import AnalysisWorker, WaveformAnalysisWorker


# task_manager Proxy — gleiche Logik wie in main.py,
# damit Methoden-Bodies unveraendert bleiben.
class _TaskManagerProxy:
    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)

task_manager = _TaskManagerProxy()


class AudioAnalysisMixin:
    """Audio analysis methods for PBWindow."""

    def _get_selected_audio_track(self):
        """Hilfsmethode: Gibt (track_id, file_path, title) des ausgewählten Audio-Tracks zurück."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Warnung] Kein Audio-Track ausgewählt.")
            return None
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                self.console_text.append("[Warnung] Audio-Track nicht in DB gefunden.")
                return None
            return (track.id, track.file_path, track.title or "Unbekannt", track.bpm)

    def _detect_key(self):
        """Erkennt die musikalische Tonart des ausgewählten Audio-Tracks."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import KeyDetectionWorker
        task = task_manager.create_task(f"Key: {title}", "Key-Erkennung (Krumhansl-Kessler)")
        worker = KeyDetectionWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Key] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[Key] Erkannt: {result.key} ({result.camelot}) Conf={result.confidence:.0%}"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[Key] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[Key] Starte Key-Erkennung für '{title}'...")

    def _analyze_lufs(self):
        """Analysiert die Lautstärke nach EBU R128."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import LUFSAnalysisWorker
        task = task_manager.create_task(f"LUFS: {title}", "LUFS-Analyse (EBU R128)")
        worker = LUFSAnalysisWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[LUFS] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[LUFS] Integrated: {result.integrated:.1f} dB, LRA: {result.loudness_range:.1f} LU, TP: {result.true_peak:.1f} dBTP"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[LUFS] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[LUFS] Starte LUFS-Analyse für '{title}'...")

    def _detect_structure(self):
        """Erkennt die Song-Struktur (INTRO/BUILDUP/DROP/BREAKDOWN/OUTRO)."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, bpm = info
        from workers.audio_analysis import StructureDetectionWorker
        task = task_manager.create_task(f"Struktur: {title}", "Song-Struktur Erkennung")
        worker = StructureDetectionWorker(track_id, file_path, bpm=bpm)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Struktur] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[Struktur] {len(result.segments)} Segmente erkannt"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[Struktur] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[Struktur] Starte Struktur-Erkennung für '{title}'...")

    def _on_audio_pool_selected(self, row, col, prev_row, prev_col):
        """Sync audio pool selection to hidden media_table + StemWorkspace."""
        if row < 0:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id_item = self.audio_pool_table.item(row, 1)
        if not aud_id_item:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id = aud_id_item.text()
        for r in range(self.media_table.rowCount()):
            item = self.media_table.item(r, 0)
            type_item = self.media_table.item(r, 1)
            if item and type_item and item.text() == aud_id and type_item.text() == "Audio":
                self.media_table.setCurrentCell(r, 0)
                break

        # Stem Workspace aktualisieren
        self._update_stem_workspace(int(aud_id))

        # Phase 4: Audio Detail Cards aktualisieren
        try:
            from database import engine, AudioTrack, Beatgrid, StructureSegment
            from sqlalchemy.orm import Session as _DBSess
            from services.key_detection_service import CAMELOT_WHEEL
            import json as _json
            audio_id = int(aud_id)
            with _DBSess(engine) as session:
                track = session.get(AudioTrack, audio_id)
                if track and hasattr(self._media_ws, '_update_audio_detail_cards'):
                    # Beat count aus Beatgrid
                    beat_count = None
                    if track.beatgrid and track.beatgrid.beat_positions:
                        try:
                            beat_count = len(_json.loads(track.beatgrid.beat_positions))
                        except Exception:
                            beat_count = None

                    # Camelot aus Key
                    camelot = CAMELOT_WHEEL.get(track.key) if track.key else None

                    # Stems Status
                    stems_status = "Ja" if track.stem_vocals_path else "Nein"

                    # Structure Segments
                    seg_rows = session.query(StructureSegment).filter_by(
                        audio_track_id=audio_id
                    ).order_by(StructureSegment.start_time).all()
                    segments = []
                    if seg_rows:
                        duration = track.duration or 1.0
                        for seg in seg_rows:
                            segments.append({
                                "label": seg.label,
                                "start": seg.start_time / duration,
                                "end": seg.end_time / duration,
                            })

                    track_data = {
                        "bpm": track.bpm,
                        "beat_count": beat_count,
                        "bpm_confidence": None,  # BPM hat kein separates Confidence-Feld
                        "key": track.key,
                        "key_confidence": track.key_confidence,
                        "camelot": camelot,
                        "mood": track.mood,
                        "energy": track.energy_curve,
                        "genre": track.genre,
                        "spectral_centroid": None,
                        "lufs": track.lufs,
                        "stems_status": stems_status,
                        "structure_segments": segments,
                    }
                    self._media_ws._update_audio_detail_cards(track_data)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug("Audio Detail Cards Update fehlgeschlagen: %s", e)

    def _analyze_selected_audio(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen analysiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Audio: {title}", "BPM + Beat-Analyse")

        worker = AnalysisWorker(track_id, title)
        worker.task_id = task.task_id
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(lambda tid, r: self._on_analysis_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_analysis_error(tid, err, task.task_id))
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Audio] {msg}"))

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)

        self._start_worker_thread(worker)

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict, task_id: str = ""):
        if not result:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_analyze.setEnabled(True)
            self.btn_analyze.setText("Audio analysieren")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        bpm = result["bpm"]
        duration = result["duration"]
        beats = len(result.get("beat_positions", []))
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result['energy_curve'])}"
        )
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        if task_id:
            task_manager.finish_task(task_id, "finished", f"{bpm} BPM, {beats} Beats")

    def _on_analysis_error(self, track_id: int, error_msg: str, task_id: str = ""):
        self.console_text.append(f"[Fehler] Audio-Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _analyze_waveform(self):
        """Startet Rekordbox-Style Frequenzanalyse für den ausgewählten Audio-Track."""
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Wellenform-Analyse nur fuer Audio-Dateien.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(
            f"Waveform: {title}", "Rekordbox Frequenz-Wellenform + Beatgrid"
        )

        worker = WaveformAnalysisWorker(track_id)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self._on_waveform_progress(pct, msg, task.task_id)
        )
        worker.finished.connect(
            lambda tid, r: self._on_waveform_finished(tid, r, title, task.task_id)
        )
        worker.error.connect(
            lambda tid, err: self._on_waveform_error(tid, err, task.task_id)
        )

        self.btn_waveform.setEnabled(False)
        self.btn_waveform.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)
        self.console_text.append(f"[Waveform] Starte Rekordbox-Analyse fuer '{title}'...")

        self._start_worker_thread(worker)

    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # update_task wird automatisch durch die Task-Engine gemacht
        self.console_text.append(f"[Waveform] {msg} ({pct}%)")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
        if not result:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_waveform.setEnabled(True)
            self.btn_waveform.setText("Rekordbox Wellenform")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        bpm = result["bpm"]
        beats = len(result.get("beat_positions", []))
        samples = result["num_samples"]
        self.console_text.append(
            f"[Waveform] Rekordbox-Analyse fertig: '{title}' | {bpm} BPM | "
            f"{beats} Beats | {samples} Wellenform-Samples (Low/Mid/High)"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Wellenform fertig: {title} | {bpm} BPM")
        self._refresh_media_table()

        # Timeline neu laden, damit die Wellenform sichtbar wird
        self.timeline_view.load_from_db()

        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{bpm} BPM, {beats} Beats, {samples} Samples"
            )

    def _on_waveform_error(self, track_id: int, error_msg: str, task_id: str):
        self.console_text.append(
            f"[Fehler] Wellenform-Analyse fehlgeschlagen (ID {track_id}): {error_msg}"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Wellenform-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)
