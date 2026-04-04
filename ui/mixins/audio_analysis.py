"""Audio-Analyse Mixin fuer PBWindow."""

import logging

from PySide6.QtCore import QObject, Signal, QTimer

from services.task_manager import TaskManagerProxy

from workers import AnalysisWorker, WaveformAnalysisWorker

logger = logging.getLogger(__name__)

task_manager = TaskManagerProxy()


class _SeqStepSignalHelper(QObject):
    """Hilfs-QObject fuer sequentielle Analyse — emittiert step_done Signal im Main-Thread.

    Noetig weil Mixins keine Signals definieren koennen (nur QObject-Subklassen).
    Das Signal wird mit QueuedConnection verbunden und garantiert Main-Thread-Ausfuehrung.
    """
    step_done = Signal(str, bool)  # step_name, success


class AudioAnalysisMixin:
    """Audio analysis methods for PBWindow."""

    def _get_selected_audio_track(self):
        """Hilfsmethode: Gibt (track_id, file_path, title, bpm) des ausgewählten Audio-Tracks zurück.

        Liest die Selection aus der audio_pool_table (primaer) oder media_table (fallback).
        """
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession

        audio_id = None

        # Primaer: audio_pool_table (das ist was der User tatsaechlich anklickt)
        pool_row = self.audio_pool_table.currentRow()
        if pool_row >= 0:
            id_item = self.audio_pool_table.item(pool_row, 1)
            if id_item and id_item.text().isdigit():
                audio_id = int(id_item.text())

        # Fallback: media_table
        if audio_id is None:
            mt_row = self.media_table.currentRow()
            if mt_row >= 0:
                type_item = self.media_table.item(mt_row, 1)
                id_item = self.media_table.item(mt_row, 0)
                if (type_item and id_item
                        and type_item.text() == "Audio"
                        and id_item.text().isdigit()):
                    audio_id = int(id_item.text())

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
        worker.finished.connect(lambda tid, res: (
            self._console_append(f"[Key] Erkannt: {res.get('key','?')} ({res.get('camelot','?')}) Conf={res.get('confidence',0):.0%}"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda tid, err: self._console_append(f"[Key] Fehler: {err}"))
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
        worker.finished.connect(lambda tid, res: (
            self._console_append(f"[LUFS] Integrated: {res.get('integrated',0):.1f} dB, LRA: {res.get('loudness_range',0):.1f} LU, TP: {res.get('true_peak',0):.1f} dBTP"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda tid, err: self._console_append(f"[LUFS] Fehler: {err}"))
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
        worker.finished.connect(lambda tid, res: (
            self._console_append(f"[Struktur] {len(res.get('segments',[]))} Segmente erkannt"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda tid, err: self._console_append(f"[Struktur] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[Struktur] Starte Struktur-Erkennung für '{title}'...")

    def _on_audio_pool_selected(self, row, col, prev_row, prev_col):
        """Sync audio pool selection to hidden media_table + StemWorkspace."""
        try:
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
            if not aud_id or not aud_id.isdigit():
                logger.warning("[AudioPool] Ungueltige Audio-ID in Zeile %d: '%s'", row, aud_id)
                return

            # Sync zur hidden media_table
            for r in range(self.media_table.rowCount()):
                item = self.media_table.item(r, 0)
                type_item = self.media_table.item(r, 1)
                if item and type_item and item.text() == aud_id and type_item.text() == "Audio":
                    self.media_table.setCurrentCell(r, 0)
                    break

            audio_id = int(aud_id)

            # Stem Workspace aktualisieren
            self._update_stem_workspace(audio_id)

            # Phase 4: Audio Detail Cards aktualisieren
            self._update_detail_cards_for_audio(audio_id)

        except (RuntimeError, OSError, ValueError) as e:
            logger.error("[AudioPool] CRASH in _on_audio_pool_selected (row=%s): %s",
                         row, e, exc_info=True)

    def _update_detail_cards_for_audio(self, audio_id: int):
        """Laedt Audio-Metadaten via Service und aktualisiert Detail-Cards."""
        try:
            if not hasattr(self._media_ws, '_update_audio_detail_cards'):
                return
            from services.ingest_service import get_audio_detail_data
            track_data = get_audio_detail_data(audio_id)
            if track_data:
                self._media_ws._update_audio_detail_cards(track_data)
        except (ImportError, OSError, RuntimeError) as e:
            logger.error("[AudioPool] Detail-Cards Update fehlgeschlagen: %s", e, exc_info=True)

    def _analyze_selected_audio(self):
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, _, title, _ = info

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
        bpm = result.get("bpm")
        duration = result.get("duration")
        if bpm is None or duration is None:
            self.btn_analyze.setEnabled(True)
            self.btn_analyze.setText("Audio analysieren")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Unvollständiges Analyse-Ergebnis")
            return
        beats = len(result.get("beat_positions", []))
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result.get('energy_curve', []))}"
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
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, _, title, _ = info

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

    # ══════════════════════════════════════════════════════════════
    # Komplett-Analyse: Alle Schritte sequentiell (crash-sicher)
    # ══════════════════════════════════════════════════════════════

    def _analyze_all_sequential(self):
        """Startet alle Audio-Analysen nacheinander fuer den ausgewaehlten Track.

        Reihenfolge: BPM/Beats -> Wellenform -> Key -> LUFS -> Struktur -> Stems
        Jeder Schritt wartet bis der vorherige fertig ist (via Queue).
        Bei Fehler: naechster Schritt wird trotzdem gestartet.
        """
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, bpm = info

        # Queue der Analyse-Schritte (Name, Worker-Factory, Signals-Setup)
        from workers import AnalysisWorker, WaveformAnalysisWorker, StemSeparationWorker
        from workers.audio_analysis import KeyDetectionWorker, LUFSAnalysisWorker, StructureDetectionWorker

        steps = [
            ("BPM/Beats", lambda: self._create_analysis_worker(track_id, title)),
            ("Wellenform", lambda: self._create_waveform_worker(track_id)),
            ("Key", lambda: self._create_key_worker(track_id, file_path)),
            ("LUFS", lambda: self._create_lufs_worker(track_id, file_path)),
            ("Struktur", lambda: self._create_structure_worker(track_id, file_path, bpm)),
            ("Stems", lambda: self._create_stem_worker(track_id)),
        ]

        self._seq_steps = steps
        self._seq_index = 0
        self._seq_done = 0
        self._seq_errors = 0
        self._seq_title = title
        self._seq_total = len(steps)

        # Signal-Helfer erstellen (QObject mit step_done Signal)
        # Noetig weil on_finish/on_error aus Worker-Thread kommen und
        # QTimer.singleShot dort nicht funktioniert.
        self._seq_helper = _SeqStepSignalHelper(self)
        self._seq_helper.step_done.connect(self._on_seq_step_done)

        # UI vorbereiten
        self._media_ws.btn_analyze_all.setEnabled(False)
        self._media_ws.btn_analyze_all.setText(f"0/{self._seq_total}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, self._seq_total)
        self.progress_bar.setValue(0)
        self.console_text.append(
            f"[Komplett] Starte Komplett-Analyse fuer '{title}' "
            f"({self._seq_total} Schritte)..."
        )

        # Ersten Schritt starten
        self._run_next_sequential_step()

    def _run_next_sequential_step(self):
        """Startet den naechsten Schritt in der sequentiellen Analyse-Queue."""
        if self._seq_index >= self._seq_total:
            # Alle Schritte fertig
            self._media_ws.btn_analyze_all.setEnabled(True)
            self._media_ws.btn_analyze_all.setText("KOMPLETT-ANALYSE")
            self.progress_bar.setVisible(False)
            self._refresh_media_table()
            errors_info = f" ({self._seq_errors} Fehler)" if self._seq_errors else ""
            self.console_text.append(
                f"[Komplett] Analyse abgeschlossen: "
                f"{self._seq_done}/{self._seq_total} OK{errors_info}"
            )
            self.status_bar.showMessage(
                f"Komplett-Analyse fertig: {self._seq_done}/{self._seq_total} | System bereit"
            )
            return

        step_name, worker_factory = self._seq_steps[self._seq_index]
        self._media_ws.btn_analyze_all.setText(
            f"{self._seq_index}/{self._seq_total}: {step_name}..."
        )
        self.progress_bar.setValue(self._seq_index)
        self.console_text.append(
            f"[Komplett] Schritt {self._seq_index + 1}/{self._seq_total}: {step_name}..."
        )

        # KRITISCH: Alle alten DB-Connections schliessen bevor der naechste Worker startet.
        # Ohne das haelt der vorherige Worker-Thread eine Connection die "database is locked"
        # verursacht wenn der naechste Worker schreibt (z.B. Struktur nach LUFS).
        try:
            from database import engine
            engine.dispose()
        except (ImportError, OSError, RuntimeError) as exc:
            logger.warning("_on_sequential_step_done: failed to dispose DB engine: %s", exc)

        try:
            worker = worker_factory()
            if worker is None:
                # Schritt uebersprungen (z.B. kein Worker noetig)
                self._seq_done += 1
                self._seq_index += 1
                self._run_next_sequential_step()
                return

            task = task_manager.create_task(
                f"Komplett: {step_name}", f"{step_name} fuer {self._seq_title}"
            )
            worker.task_id = task.task_id

            # Bei Erfolg ODER Fehler: Signal emittieren das im Main-Thread ankommt.
            # on_finish/on_error Lambdas laufen im Worker-Thread (trotz QueuedConnection)
            # weil PySide6 Python-Lambdas nicht als QObject-Slots behandelt.
            # Stattdessen: _seq_helper.step_done.emit() — das ist ein echtes Qt Signal
            # das garantiert im Main-Thread via AutoConnection ankommt.
            helper = self._seq_helper
            self._start_worker_thread(
                worker,
                on_finish=lambda *args, _sn=step_name, _h=helper: _h.step_done.emit(_sn, True),
                on_error=lambda *args, _sn=step_name, _h=helper: _h.step_done.emit(_sn, False),
            )
        except (RuntimeError, OSError, ValueError) as e:
            logger.error("[Komplett] Fehler beim Starten von %s: %s", step_name, e)
            self.console_text.append(f"[Komplett] {step_name} konnte nicht gestartet werden: {e}")
            self._seq_errors += 1
            self._seq_index += 1
            # Trotzdem weiter — naechsten Schritt nach kurzem Delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._run_next_sequential_step)

    def _on_seq_step_done(self, step_name: str, success: bool):
        """Callback wenn ein sequentieller Schritt fertig ist.

        Wird IMMER im Main-Thread aufgerufen (via _seq_helper.step_done Signal).
        QTimer.singleShot funktioniert hier zuverlaessig.
        """
        if success:
            self._seq_done += 1
            self.console_text.append(f"[Komplett] {step_name} OK")
        else:
            self._seq_errors += 1
            self.console_text.append(f"[Komplett] {step_name} FEHLER (uebersprungen)")

        self._seq_index += 1
        # Main-Thread — QTimer funktioniert zuverlaessig
        QTimer.singleShot(500, self._run_next_sequential_step)

    # ── Worker-Factories fuer sequentielle Analyse ──

    def _create_analysis_worker(self, track_id: int, title: str):
        worker = AnalysisWorker(track_id, title)
        return worker

    def _create_waveform_worker(self, track_id: int):
        worker = WaveformAnalysisWorker(track_id)
        return worker

    def _create_key_worker(self, track_id: int, file_path: str):
        from workers.audio_analysis import KeyDetectionWorker
        return KeyDetectionWorker(track_id, file_path)

    def _create_lufs_worker(self, track_id: int, file_path: str):
        from workers.audio_analysis import LUFSAnalysisWorker
        return LUFSAnalysisWorker(track_id, file_path)

    def _create_structure_worker(self, track_id: int, file_path: str, bpm: float):
        from workers.audio_analysis import StructureDetectionWorker
        return StructureDetectionWorker(track_id, file_path, bpm=bpm)

    def _create_stem_worker(self, track_id: int):
        from workers import StemSeparationWorker
        return StemSeparationWorker(track_id)
