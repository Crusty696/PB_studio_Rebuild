"""AudioAnalysisController — Refactored from AudioAnalysisMixin."""

import logging
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from services.task_manager import TaskManagerProxy
from workers import AnalysisWorker, WaveformAnalysisWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()

class _SeqStepSignalHelper(QObject):
    """Hilfs-QObject fuer sequentielle Analyse."""
    step_done = Signal(str, bool)  # step_name, success

class AudioAnalysisController(PBComponent):
    """Audio analysis methods for PBWindow."""

    def _get_selected_audio_track(self):
        """Hilfsmethode: Gibt (track_id, file_path, title, bpm) des ausgewaehlten Audio-Tracks zurueck."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession

        audio_id = None

        # 1. Versuche Auswahl aus der Audio-Pool Tabelle (QTableView)
        view = self.window.audio_pool_table
        model = view.model()
        indexes = view.selectionModel().selectedRows()

        if indexes:
            row = indexes[0].row()
            val = model.index(row, 1).data()
            if val and str(val).isdigit():
                audio_id = int(val)

        if audio_id is None:
            self.window.console_text.append("[Warnung] Kein Audio-Track ausgewaehlt.")
            return None

        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                self.window.console_text.append("[Warnung] Audio-Track nicht in DB gefunden.")
                return None
            return (track.id, track.file_path, track.title or "Unbekannt", track.bpm)

    def _detect_key(self):
        """Erkennt die musikalische Tonart des ausgewaehlten Audio-Tracks."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import KeyDetectionWorker
        task = task_manager.create_task(f"Key: {title}", "Key-Erkennung (Krumhansl-Kessler)")
        worker = KeyDetectionWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self.window._console_append(f"[Key] {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Key] Erkannt: {res.get('key','?')} ({res.get('camelot','?')}) Conf={res.get('confidence',0):.0%}"),
                self.window.media_table_controller._refresh_media_table_debounced(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self.window._console_append(f"[Key] Fehler: {err}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Key] Starte Key-Erkennung fuer '{title}'...")

    def _analyze_lufs(self):
        """Analysiert die Lautstaerke nach EBU R128."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import LUFSAnalysisWorker
        task = task_manager.create_task(f"LUFS: {title}", "LUFS-Analyse (EBU R128)")
        worker = LUFSAnalysisWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self.window._console_append(f"[LUFS] {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[LUFS] Integrated: {res.get('integrated',0):.1f} dB, LRA: {res.get('loudness_range',0):.1f} LU, TP: {res.get('true_peak',0):.1f} dBTP"),
                self.window.media_table_controller._refresh_media_table_debounced(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self.window._console_append(f"[LUFS] Fehler: {err}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[LUFS] Starte LUFS-Analyse fuer '{title}'...")

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
        worker.progress.connect(
            lambda pct, msg: self.window._console_append(f"[Struktur] {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Struktur] {len(res.get('segments',[]))} Segmente erkannt"),
                self.window.media_table_controller._refresh_media_table_debounced(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self.window._console_append(f"[Struktur] Fehler: {err}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Struktur] Starte Struktur-Erkennung fuer '{title}'...")

    def _on_audio_pool_selected(self, row, col, prev_row, prev_col):
        """Sync audio pool selection to StemWorkspace and detail cards."""
        try:
            if row < 0:
                self.window.stem_player.stop()
                if hasattr(self.window, "stem_workspace"):
                    self.window.stem_workspace.update_for_track(None, None)
                if hasattr(self.window, "_stems_ws"):
                    self.window._stems_ws.update_analysis(None)
                return

            view = self.window.audio_pool_table
            model = view.model()
            aud_id_val = model.index(row, 1).data()

            if not aud_id_val or not str(aud_id_val).isdigit():
                return

            audio_id = int(aud_id_val)
            self.window.stems._update_stem_workspace(audio_id)
            self._update_detail_cards_for_audio(audio_id)

        except (RuntimeError, OSError, ValueError) as e:
            logger.error("[AudioPool] CRASH in _on_audio_pool_selected (row=%s): %s",
                         row, e, exc_info=True)

    def _update_detail_cards_for_audio(self, audio_id: int):
        """Laedt Audio-Metadaten via Service und aktualisiert Detail-Cards."""
        try:
            if not hasattr(self.window._media_ws, '_update_audio_detail_cards'):
                return
            from services.ingest_service import get_audio_detail_data
            track_data = get_audio_detail_data(audio_id)
            if track_data:
                self.window._media_ws._update_audio_detail_cards(track_data)
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
        worker.started.connect(self._on_analysis_started, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            lambda tid, r: self._on_analysis_finished(tid, r, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self._on_analysis_error(tid, err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.progress.connect(
            lambda pct, msg: self.window._console_append(f"[Audio] {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )

        self.window.btn_analyze.setEnabled(False)
        self.window.btn_analyze.setText("Analyse laeuft...")
        self.window.progress_bar.setVisible(True)
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_analysis_started(self, track_id: int, title: str):
        self.window.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.window.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict, task_id: str = ""):
        if not result:
            self.window.btn_analyze.setEnabled(True)
            self.window.btn_analyze.setText("Audio analysieren")
            self.window.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        bpm = result.get("bpm")
        duration = result.get("duration")
        if bpm is None or duration is None:
            self.window.btn_analyze.setEnabled(True)
            self.window.btn_analyze.setText("Audio analysieren")
            self.window.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Unvollstaendiges Analyse-Ergebnis")
            return
        beats = len(result.get("beat_positions", []))
        self.window.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result.get('energy_curve', []))}"
        )
        self.window.btn_analyze.setEnabled(True)
        self.window.btn_analyze.setText("Audio analysieren")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self.window.media_table_controller._refresh_media_table_debounced()
        if task_id:
            task_manager.finish_task(task_id, "finished", f"{bpm} BPM, {beats} Beats")

    def _on_analysis_error(self, track_id: int, error_msg: str, task_id: str = ""):
        self.window.console_text.append(f"[Fehler] Audio-Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.window.btn_analyze.setEnabled(True)
        self.window.btn_analyze.setText("Audio analysieren")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage("Analyse-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _analyze_waveform(self):
        """Startet Rekordbox-Style Frequenzanalyse fuer den ausgewaehlten Audio-Track."""
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
            lambda pct, msg: self._on_waveform_progress(pct, msg, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, r: self._on_waveform_finished(tid, r, title, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self._on_waveform_error(tid, err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )

        self.window.btn_waveform.setEnabled(False)
        self.window.btn_waveform.setText("Analyse laeuft...")
        self.window.progress_bar.setVisible(True)
        self.window.console_text.append(f"[Waveform] Starte Rekordbox-Analyse fuer '{title}'...")
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # B-291: progress_bar live binden — vorher leerer Slot.
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        self.window.progress_bar.setFormat(f"Waveform: %p%% — {msg[:50]}")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
        if not result:
            self.window.btn_waveform.setEnabled(True)
            self.window.btn_waveform.setText("Rekordbox Wellenform")
            self.window.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        # M-58 Fix: Use .get() with safe defaults to prevent KeyError in UI thread
        bpm = result.get("bpm", 0)
        beats = len(result.get("beat_positions", []))
        samples = result.get("num_samples", 0)
        self.window.console_text.append(
            f"[Waveform] Rekordbox-Analyse fertig: '{title}' | {bpm} BPM | "
            f"{beats} Beats | {samples} Wellenform-Samples (Low/Mid/High)"
        )
        self.window.btn_waveform.setEnabled(True)
        self.window.btn_waveform.setText("Rekordbox Wellenform")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage(f"Wellenform fertig: {title} | {bpm} BPM")
        self.window.media_table_controller._refresh_media_table_debounced()
        # H-40 Fix: Defer load_from_db to prevent UI freeze on large projects
        QTimer.singleShot(100, self.window.timeline_view.load_from_db)

        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{bpm} BPM, {beats} Beats, {samples} Samples"
            )

    def _on_waveform_error(self, track_id: int, error_msg: str, task_id: str):
        self.window.console_text.append(
            f"[Fehler] Wellenform-Analyse fehlgeschlagen (ID {track_id}): {error_msg}"
        )
        self.window.btn_waveform.setEnabled(True)
        self.window.btn_waveform.setText("Rekordbox Wellenform")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage("Wellenform-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _analyze_all_sequential(self):
        """Startet alle Audio-Analysen nacheinander fuer den ausgewaehlten Track."""
        # H-37 FIX: Guard against double-click race condition
        if getattr(self, '_seq_running', False):
            logger.warning("[Komplett] Analyse laeuft bereits, Doppel-Klick ignoriert.")
            return

        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, bpm = info

        steps = [
            ("BPM/Beats", lambda: self._create_analysis_worker(track_id, title)),
            ("Wellenform", lambda: self._create_waveform_worker(track_id)),
            ("Key", lambda: self._create_key_worker(track_id, file_path)),
            ("LUFS", lambda: self._create_lufs_worker(track_id, file_path)),
            ("Struktur", lambda: self._create_structure_worker(track_id, file_path, bpm)),
            ("Stems", lambda: self._create_stem_worker(track_id)),
        ]

        # H-37 FIX: Set running flag to prevent race condition
        self._seq_running = True
        self._seq_steps = steps
        self._seq_index = 0
        self._seq_done = 0
        self._seq_errors = 0
        self._seq_title = title
        self._seq_total = len(steps)

        # L-36 Fix: Disconnect old helper signals before creating new one
        if hasattr(self, '_seq_helper') and self._seq_helper is not None:
            try:
                self._seq_helper.step_done.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected or deleted
        self._seq_helper = _SeqStepSignalHelper(self.window)
        self._seq_helper.step_done.connect(self._on_seq_step_done)

        self.window._media_ws.btn_analyze_all.setEnabled(False)
        self.window._media_ws.btn_analyze_all.setText(f"0/{self._seq_total}...")
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setRange(0, self._seq_total)
        self.window.progress_bar.setValue(0)
        self.window.console_text.append(
            f"[Komplett] Starte Komplett-Analyse fuer '{title}' ({self._seq_total} Schritte)..."
        )
        self._run_next_sequential_step()

    def _run_next_sequential_step(self):
        """Startet den naechsten Schritt in der sequentiellen Analyse-Queue."""
        try:
            self._run_next_sequential_step_inner()
        except Exception as exc:
            # K11 FIX: _seq_running IMMER zuruecksetzen bei unerwarteten Exceptions,
            # damit der Button nicht dauerhaft blockiert bleibt.
            logger.error("[Komplett] Unerwarteter Fehler in Analyse-Kette: %s", exc, exc_info=True)
            self._seq_running = False
            try:
                self.window._media_ws.btn_analyze_all.setEnabled(True)
                self.window._media_ws.btn_analyze_all.setText("KOMPLETT-ANALYSE")
                self.window.progress_bar.setVisible(False)
                self.window.console_text.append(
                    f"[Komplett] Analyse abgebrochen wegen Fehler: {exc}"
                )
            except Exception:
                pass  # UI evtl. schon zerstoert

    def _run_next_sequential_step_inner(self):
        """Innere Implementierung der sequentiellen Analyse-Queue."""
        # F-046 Fix: Abbrechen wenn Fenster nicht mehr da oder versteckt (Shutdown-Schutz)
        if not self.window or not self.window.isVisible():
            logger.info("[Komplett] Analyse-Kette abgebrochen (Fenster nicht aktiv).")
            self._seq_running = False
            return

        if self._seq_index >= self._seq_total:
            # H-37 FIX: Reset running flag on completion
            self._seq_running = False
            self.window._media_ws.btn_analyze_all.setEnabled(True)
            self.window._media_ws.btn_analyze_all.setText("KOMPLETT-ANALYSE")
            self.window.progress_bar.setVisible(False)
            self.window.media_table_controller._refresh_media_table_debounced()
            errors_info = f" ({self._seq_errors} Fehler)" if self._seq_errors else ""
            self.window.console_text.append(
                f"[Komplett] Analyse abgeschlossen: {self._seq_done}/{self._seq_total} OK{errors_info}"
            )
            self.window.status_bar.showMessage(
                f"Komplett-Analyse fertig: {self._seq_done}/{self._seq_total} | System bereit"
            )
            return

        step_name, worker_factory = self._seq_steps[self._seq_index]
        self.window._media_ws.btn_analyze_all.setText(f"{self._seq_index}/{self._seq_total}: {step_name}...")
        self.window.progress_bar.setValue(self._seq_index)
        self.window.console_text.append(f"[Komplett] Schritt {self._seq_index + 1}/{self._seq_total}: {step_name}...")

        # K11 FIX: engine.dispose() ENTFERNT — schloss ALLE Pool-Connections
        # inklusive derer von anderen Threads. Connection-Leaks werden jetzt
        # durch korrekte Session-Nutzung (with-Blocks) verhindert, nicht durch
        # Pool-Reset zwischen Schritten.

        try:
            worker = worker_factory()
            if worker is None:
                self._seq_done += 1
                self._seq_index += 1
                self._run_next_sequential_step()
                return

            task = task_manager.create_task(f"Komplett: {step_name}", f"{step_name} fuer {self._seq_title}")
            worker.task_id = task.task_id
            helper = self._seq_helper
            self.window.worker_dispatcher._start_worker_thread(
                worker,
                on_finish=lambda *args, _sn=step_name, _h=helper: _h.step_done.emit(_sn, True),
                on_error=lambda *args, _sn=step_name, _h=helper: _h.step_done.emit(_sn, False),
            )
        except (RuntimeError, OSError, ValueError) as e:
            logger.error("[Komplett] Fehler beim Starten von %s: %s", step_name, e)
            self.window.console_text.append(f"[Komplett] {step_name} konnte nicht gestartet werden: {e}")
            self._seq_errors += 1
            self._seq_index += 1
            QTimer.singleShot(500, self._run_next_sequential_step)

    def _on_seq_step_done(self, step_name: str, success: bool):
        # F-046 Fix: Abbrechen wenn Fenster nicht mehr aktiv
        if not self.window or not self.window.isVisible():
            # K11 FIX: _seq_running zuruecksetzen auch bei Fenster-Abbruch
            self._seq_running = False
            return

        if success:
            self._seq_done += 1
            self.window.console_text.append(f"[Komplett] {step_name} OK")
        else:
            self._seq_errors += 1
            self.window.console_text.append(f"[Komplett] {step_name} FEHLER (uebersprungen)")

        self._seq_index += 1
        # F-046 Fix: Kuerzerer Timer fuer Responsiveness + Guard
        if self.window.isVisible():
            QTimer.singleShot(100, self._run_next_sequential_step)

    def _create_analysis_worker(self, track_id: int, title: str):
        return AnalysisWorker(track_id, title)

    def _create_waveform_worker(self, track_id: int):
        return WaveformAnalysisWorker(track_id)

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
