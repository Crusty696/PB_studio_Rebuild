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
        """B-293: Checkbox-first, Maus-Selection-Fallback. Symmetrisch zu Video-Helper."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession
        from sqlalchemy import select  # B-625

        view = self.window.audio_pool_table
        model = view.model()

        audio_id = None
        if hasattr(model, "get_checked_ids"):
            checked = list(model.get_checked_ids() or [])
            if checked:
                try:
                    audio_id = int(checked[0])
                except (ValueError, TypeError):
                    audio_id = None

        if audio_id is None:
            indexes = view.selectionModel().selectedRows()
            if indexes:
                val = model.index(indexes[0].row(), 1).data()
                if val and str(val).isdigit():
                    audio_id = int(val)

        if audio_id is None:
            self.window.console_text.append(
                "[Warnung] Kein Audio-Track ausgewaehlt (weder Checkbox noch Maus-Selection)."
            )
            return None

        with DBSession(engine) as session:
            # B-625: nur Skalar-Spalten selektieren statt session.get() —
            # verhindert eager-load der JSON-Blob-Spalten (waveform_data/
            # beatgrid), die den Qt-Main-Thread einfrieren.
            track = session.execute(
                select(
                    AudioTrack.id,
                    AudioTrack.file_path,
                    AudioTrack.title,
                    AudioTrack.bpm,
                ).where(AudioTrack.id == audio_id)
            ).first()
            if not track:
                self.window.console_text.append("[Warnung] Audio-Track nicht in DB gefunden.")
                return None
            return (track.id, track.file_path, track.title or "Unbekannt", track.bpm)

    def _get_selected_audio_tracks(self) -> list[int]:
        """B-293 Batch-Variante. Liefert Track-IDs (NICHT DB-aufgeloest — Caller
        muss IDs selbst dereferenzieren). Checkbox-first, Maus-Selection
        fallback. Caller MUSS leere Liste selbst behandeln (kein Warning).
        """
        view = self.window.audio_pool_table
        model = view.model()

        if hasattr(model, "get_checked_ids"):
            checked = list(model.get_checked_ids() or [])
            if checked:
                return [int(x) for x in checked if str(x).isdigit()]

        indexes = view.selectionModel().selectedRows()
        ids: list[int] = []
        for idx in indexes:
            val = model.index(idx.row(), 1).data()
            if val and str(val).isdigit():
                ids.append(int(val))
        return ids

    def _analyze_audio_v2(self):
        """OTK-018: faehrt die strict-sequential Audio-V2-Pipeline (Orchestrator)
        fuer den ausgewaehlten Track — Demucs-Stems + stem-geroutete Analyse
        (Onset=drums, Key=bass+other, Structure=stem-bass) in einem Durchlauf,
        resume-faehig. Opt-in: bindet die portierte V2-Pipeline ein, ohne den
        bestehenden Einzel-Service-Pfad (_detect_key/_analyze_lufs/...) zu aendern.
        """
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
        task = task_manager.create_task(f"Audio-V2: {title}", "Audio-V2 Pipeline (strict-sequential)")
        worker = AudioPipelineV2Worker(track_id, file_path)
        worker.task_id = task.task_id

        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setRange(0, 100)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Audio-V2: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Audio-V2] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Audio-V2] Pipeline fertig: {len(res)} Stages"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Audio-V2] Fehler: {err}"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Audio-V2] Starte Pipeline fuer '{title}'...")

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

        self.window.btn_key_detect.setEnabled(False)
        self.window.btn_key_detect.setText("Tonart laeuft...")
        self.window.progress_bar.setVisible(True)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Tonart: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Key] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Key] Erkannt: {res.get('key','?')} ({res.get('camelot','?')}) Conf={res.get('confidence',0):.0%}"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.btn_key_detect.setEnabled(True),
                self.window.btn_key_detect.setText("Tonart"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Key] Fehler: {err}"),
                self.window.btn_key_detect.setEnabled(True),
                self.window.btn_key_detect.setText("Tonart"),
                self.window.progress_bar.setVisible(False),
            ),
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

        self.window.btn_lufs_analyze.setEnabled(False)
        self.window.btn_lufs_analyze.setText("LUFS laeuft...")
        self.window.progress_bar.setVisible(True)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"LUFS: %p%% — {msg[:50]}"),
                self.window._console_append(f"[LUFS] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[LUFS] Integrated: {res.get('integrated',0):.1f} dB, LRA: {res.get('loudness_range',0):.1f} LU, TP: {res.get('true_peak',0):.1f} dBTP"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.btn_lufs_analyze.setEnabled(True),
                self.window.btn_lufs_analyze.setText("LUFS"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[LUFS] Fehler: {err}"),
                self.window.btn_lufs_analyze.setEnabled(True),
                self.window.btn_lufs_analyze.setText("LUFS"),
                self.window.progress_bar.setVisible(False),
            ),
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

        self.window.btn_structure_detect.setEnabled(False)
        self.window.btn_structure_detect.setText("Songstruktur laeuft...")
        self.window.progress_bar.setVisible(True)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Songstruktur: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Struktur] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Struktur] {len(res.get('segments',[]))} Segmente erkannt"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.btn_structure_detect.setEnabled(True),
                self.window.btn_structure_detect.setText("Songstruktur"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Struktur] Fehler: {err}"),
                self.window.btn_structure_detect.setEnabled(True),
                self.window.btn_structure_detect.setText("Songstruktur"),
                self.window.progress_bar.setVisible(False),
            ),
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
            # UX-Fix (User 2026-07-17, Klasse B-472): vorher stiller Abbruch —
            # Button wirkte tot, wenn keine Zeile markiert war.
            self.window.console_text.append(
                "[Warnung] Kein Audio ausgewählt — bitte zuerst einen Track "
                "in der Audio-Liste anklicken."
            )
            self.window.status_bar.showMessage("Kein Audio ausgewählt", 5000)
            return
        # OTK-018: Audio-V2 strict-sequential Pipeline als Default-Analysepfad
        # (Demucs-Stems + stem-geroutete Analyse). Reversibel via Setting
        # audio.v2_default=false -> faellt auf den klassischen Einzel-Service-
        # AnalysisWorker zurueck. Der Tools-Menue-Eintrag bleibt unabhaengig.
        try:
            from services.settings_store import get_settings_store
            v2_default = get_settings_store().get_nested("audio", "v2_default", default=True)
        except Exception:
            v2_default = True
        if v2_default:
            self.window._console_append("[Audio] V2-Pipeline (Default) — stem-geroutete Analyse")
            self._analyze_audio_v2()
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
            f"Waveform: {title}", "Rekordbox Frequenz-Wellenform (3-Band)"
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
        self.window.btn_waveform.setText("Wellenform laeuft...")
        self.window.progress_bar.setVisible(True)
        self.window.console_text.append(f"[Waveform] Starte Rekordbox-Analyse fuer '{title}'...")
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # B-291: progress_bar live binden — vorher leerer Slot.
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        self.window.progress_bar.setFormat(f"Wellenform: %p%% — {msg[:50]}")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
        if not result:
            self.window.btn_waveform.setEnabled(True)
            self.window.btn_waveform.setText("Wellenform")
            self.window.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        # M-58 Fix: Use .get() with safe defaults to prevent KeyError in UI thread
        # B-501: FrequencyAnalyzer liefert keine beat_positions mehr; "bpm" ist
        # nur noch der durchgereichte DB-Wert (von BeatAnalysisService) oder fehlt.
        bpm = result.get("bpm", 0)
        samples = result.get("num_samples", 0)
        self.window.console_text.append(
            f"[Waveform] Rekordbox-Analyse fertig: '{title}' | {bpm} BPM | "
            f"{samples} Wellenform-Samples (Low/Mid/High)"
        )
        self.window.btn_waveform.setEnabled(True)
        self.window.btn_waveform.setText("Wellenform")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage(f"Wellenform fertig: {title} | {bpm} BPM")
        self.window.media_table_controller._refresh_media_table_debounced()
        # H-40 Fix: Defer load_from_db to prevent UI freeze on large projects
        QTimer.singleShot(100, self.window.timeline_view.load_from_db)

        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{bpm} BPM, {samples} Samples"
            )

    def _on_waveform_error(self, track_id: int, error_msg: str, task_id: str):
        self.window.console_text.append(
            f"[Fehler] Wellenform-Analyse fehlgeschlagen (ID {track_id}): {error_msg}"
        )
        self.window.btn_waveform.setEnabled(True)
        self.window.btn_waveform.setText("Wellenform")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage("Wellenform-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _analyze_all_v2_batch(self, track_ids):
        """OTK-018: faehrt die Audio-V2-Pipeline sequentiell fuer alle gewaehlten
        Tracks (ein V2-Worker nach dem anderen, kein GPU-Parallelismus). Default-
        Pfad des KOMPLETT-ANALYSE-Buttons (Setting audio.v2_default)."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session
        from sqlalchemy import select  # B-625/B-090
        queue = []
        with Session(engine) as s:
            # B-625/B-090: nur Skalar-Spalten selektieren statt ORM-Voll-Laden —
            # AudioTrack.beatgrid/waveform_data sind lazy='joined' und wuerden
            # bei jedem Track die JSON-Blobs eager mitziehen. Das lief hier in
            # einer Schleife auf dem Qt-Main-Thread (Klick-Handler ohne Worker),
            # der Freeze skalierte also linear mit der Trackzahl. Gebraucht
            # werden ohnehin nur file_path/title. Gleiches Muster wie in
            # _get_selected_track (:51) und _batch_next (:648).
            rows = s.execute(
                select(
                    AudioTrack.id,
                    AudioTrack.file_path,
                    AudioTrack.title,
                ).where(AudioTrack.id.in_(list(track_ids)))
            ).all()
            by_id = {r.id: r for r in rows}
            # Reihenfolge der Auswahl beibehalten (IN() garantiert sie nicht).
            for tid in track_ids:
                r = by_id.get(tid)
                if r and r.file_path:
                    queue.append((tid, r.file_path, r.title or str(tid)))
        if not queue:
            self.window.console_text.append("[Komplett-Analyse V2] Keine gueltigen Tracks.")
            return
        self._v2_queue = queue
        self._v2_total = len(queue)
        self._v2_done = 0
        self._seq_running = True
        self.window._media_ws.btn_analyze_all.setEnabled(False)
        self.window.console_text.append(
            f"[Komplett-Analyse V2] Starte V2-Pipeline fuer {self._v2_total} Track(s)."
        )
        self._v2_next()

    def _v2_next(self):
        if not getattr(self, "_v2_queue", None):
            self._seq_running = False
            try:
                self.window._media_ws.btn_analyze_all.setEnabled(True)
                self.window._media_ws.btn_analyze_all.setText("KOMPLETT-ANALYSE")
                self.window.progress_bar.setVisible(False)
                self.window.media_table_controller._refresh_media_table_debounced()
            except (RuntimeError, AttributeError):
                pass
            self.window.console_text.append(
                f"[Komplett-Analyse V2] Fertig: {self._v2_done}/{getattr(self, '_v2_total', 0)} Track(s)."
            )
            return
        track_id, file_path, title = self._v2_queue.pop(0)
        from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
        task = task_manager.create_task(f"Audio-V2: {title}", "Audio-V2 Pipeline (strict-sequential)")
        worker = AudioPipelineV2Worker(track_id, file_path)
        worker.task_id = task.task_id
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setRange(0, 100)
        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Audio-V2: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Audio-V2] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: self._v2_advance(),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Audio-V2] Fehler: {err}"),
                self._v2_advance(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Audio-V2] Starte Pipeline fuer '{title}'...")

    def _v2_advance(self):
        self._v2_done = getattr(self, "_v2_done", 0) + 1
        self._v2_next()

    def _analyze_all_sequential(self):
        """Startet alle Audio-Analysen nacheinander fuer alle gewaehlten Tracks.

        B-293 Phase B + R-23 C-1/C-2 Fix: TRUE multi-track sequential.
        Checkbox-first via Plural-Helper, Fallback "alle Tracks im Pool"
        wenn Checkbox leer. ALLE track_ids werden seriell durchlaufen
        (Batch-Queue _batch_queue + _process_next_batch_track), pro Track
        die 6 Steps (BPM/Waveform/Key/LUFS/Structure/Stems).
        """
        # H-37 FIX: Guard against double-click race condition
        if getattr(self, '_seq_running', False):
            logger.warning("[Komplett] Analyse laeuft bereits, Doppel-Klick ignoriert.")
            return

        track_ids = self._get_selected_audio_tracks()
        if not track_ids:
            # Fallback: ALL tracks in pool
            model = self.window.audio_pool_table.model()
            for row in range(model.rowCount()):
                val = model.index(row, 1).data()
                if val and str(val).isdigit():
                    track_ids.append(int(val))
            if track_ids:
                self.window.console_text.append(
                    f"[Komplett-Analyse] Keine Checkbox aktiv — verwende alle {len(track_ids)} Tracks im Pool."
                )
        if not track_ids:
            self.window.console_text.append("[Komplett-Analyse] Keine Audio-Tracks im Pool.")
            return

        # OTK-018: Audio-V2 strict-sequential Pipeline als Default-Analysepfad
        # (Demucs-Stems + stem-geroutete Onset/Key/Structure). Reversibel via
        # Setting audio.v2_default=false -> klassischer 6-Step-Batch.
        try:
            from services.settings_store import get_settings_store
            v2_default = get_settings_store().get_nested("audio", "v2_default", default=True)
        except Exception:
            v2_default = True
        if v2_default:
            self._analyze_all_v2_batch(track_ids)
            return

        # Multi-Track-Queue: ein Track nach dem anderen.
        self._batch_queue = list(track_ids)
        self._batch_total = len(track_ids)
        self._batch_index = 0
        self._batch_track_done = 0
        self._batch_track_errors = 0
        self.window.console_text.append(
            f"[Komplett-Analyse] Starte Batch mit {self._batch_total} Track(s)."
        )

        # Helper EINMAL pro Batch initialisieren (vermeidet Reconnect-Kosten).
        # L-36 Fix: Disconnect old helper signals before creating new one
        if hasattr(self, '_seq_helper') and self._seq_helper is not None:
            try:
                self._seq_helper.step_done.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected or deleted
        self._seq_helper = _SeqStepSignalHelper(self.window)
        self._seq_helper.step_done.connect(self._on_seq_step_done)

        # H-37 FIX: Set running flag once for whole batch
        self._seq_running = True
        self.window._media_ws.btn_analyze_all.setEnabled(False)

        self._process_next_batch_track()

    def _process_next_batch_track(self):
        """B-293 R-23 C-1 Fix: Startet den naechsten Track der Batch-Queue.

        Wird zu Beginn jedes Track-Durchlaufs gerufen sowie nach letztem Step des
        vorherigen Tracks. Leere Queue -> Batch-Finish (UI-Reset).
        """
        # Guard gegen UI-Shutdown waehrend Batch
        if not self.window or not self.window.isVisible():
            self._seq_running = False
            return

        # Batch fertig?
        if not getattr(self, "_batch_queue", None):
            self._seq_running = False
            try:
                self.window._media_ws.btn_analyze_all.setEnabled(True)
                self.window._media_ws.btn_analyze_all.setText("KOMPLETT-ANALYSE")
                self.window.progress_bar.setVisible(False)
                self.window.media_table_controller._refresh_media_table_debounced()
            except Exception:  # noqa: BLE001
                pass
            self.window.console_text.append(
                f"[Komplett-Analyse] Batch fertig — {self._batch_total} Track(s) durchlaufen "
                f"({self._batch_track_done} OK, {self._batch_track_errors} mit Fehlern)."
            )
            self.window.status_bar.showMessage(
                f"Komplett-Analyse fertig: {self._batch_total} Track(s) | System bereit"
            )
            return

        # Nimm den naechsten Track
        track_id_raw = self._batch_queue.pop(0)
        self._batch_index += 1

        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession
        from sqlalchemy import select  # B-625
        with DBSession(engine) as session:
            # B-625: nur Skalar-Spalten selektieren statt session.get() —
            # verhindert eager-load der JSON-Blob-Spalten (waveform_data/
            # beatgrid), die den Qt-Main-Thread (QTimer) einfrieren.
            track = session.execute(
                select(
                    AudioTrack.id,
                    AudioTrack.file_path,
                    AudioTrack.title,
                    AudioTrack.bpm,
                ).where(AudioTrack.id == track_id_raw)
            ).first()
            if not track:
                self.window.console_text.append(
                    f"[Komplett-Analyse] Track {track_id_raw} nicht in DB gefunden — uebersprungen."
                )
                self._batch_track_errors += 1
                # Weiter mit naechstem (defer via Timer, damit UI atmen kann)
                QTimer.singleShot(50, self._process_next_batch_track)
                return
            track_id = track.id
            file_path = track.file_path
            title = track.title or "Unbekannt"
            bpm = track.bpm

        self.window.console_text.append(
            f"[Komplett-Analyse] Track {self._batch_index}/{self._batch_total}: {title}"
        )
        self._run_audio_steps_for_track(track_id, file_path, title, bpm)

    def _run_audio_steps_for_track(self, track_id: int, file_path: str, title: str, bpm):
        """B-293 R-23 C-1 Fix: Setzt _seq_*-State fuer EINEN Track auf und
        kickt die 8-Step-Chain. Nach Step 8 chained _on_seq_step_done bzw.
        _run_next_sequential_step_inner zu _process_next_batch_track().
        """
        step_specs = [
            ("bpm_detection", "BPM/Beats", lambda: self._create_analysis_worker(track_id, title)),
            ("waveform_analysis", "Wellenform", lambda: self._create_waveform_worker(track_id)),
            ("key_detection", "Key", lambda: self._create_key_worker(track_id, file_path)),
            ("lufs_analysis", "LUFS", lambda: self._create_lufs_worker(track_id, file_path)),
            ("mood_genre_classify", "Mood/Genre", lambda: self._create_classify_worker(track_id, file_path, bpm)),
            ("spectral_analysis", "Spektral", lambda: self._create_spectral_worker(track_id, file_path)),
            ("structure_detection", "Struktur", lambda: self._create_structure_worker(track_id, file_path, bpm)),
            ("stem_separation", "Stems", lambda: self._create_stem_worker(track_id)),
        ]
        # B-458 / User-Anweisung: Bereits gemachte Analysen nicht ueberspringen, sondern nochmals ausfuehren.
        steps = [(name, factory) for key, name, factory in step_specs]

        self._seq_steps = steps
        self._seq_index = 0
        self._seq_done = 0
        self._seq_errors = 0
        self._seq_title = title
        self._seq_total = len(steps)

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
            # B-293 R-23 C-1 Fix: Track fertig — Batch-Bilanz updaten und
            # zum naechsten Track der Queue weiterchainen.
            errors_info = f" ({self._seq_errors} Fehler)" if self._seq_errors else ""
            self.window.console_text.append(
                f"[Komplett] Track '{self._seq_title}' abgeschlossen: "
                f"{self._seq_done}/{self._seq_total} OK{errors_info}"
            )
            if self._seq_errors:
                self._batch_track_errors += 1
            else:
                self._batch_track_done += 1
            # Chain to next batch track (handles "queue empty -> reset UI" itself)
            QTimer.singleShot(100, self._process_next_batch_track)
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

    def _classify_mood(self):
        """Klassifiziert die Stimmung und das Genre des ausgewaehlten Audio-Tracks."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, bpm = info
        from workers.audio_analysis import AudioClassifyWorker
        task = task_manager.create_task(f"Classify: {title}", "Mood/Genre AI")
        worker = AudioClassifyWorker(track_id, file_path, bpm=bpm)
        worker.task_id = task.task_id

        self.window.btn_mood_classify.setEnabled(False)
        self.window.btn_mood_classify.setText("Mood/Genre laeuft...")
        self.window.progress_bar.setVisible(True)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Mood/Genre: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Classify] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Classify] Genre: {res.get('genre', '?')}, Mood: {res.get('mood', '?')}"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.btn_mood_classify.setEnabled(True),
                self.window.btn_mood_classify.setText("Mood / Genre"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Classify] Fehler: {err}"),
                self.window.btn_mood_classify.setEnabled(True),
                self.window.btn_mood_classify.setText("Mood / Genre"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Classify] Starte Mood/Genre-Klassifikation fuer '{title}'...")

    def _analyze_spectral(self):
        """Analysiert das Spektrum (8-Band Frequenzanalyse) des ausgewaehlten Audio-Tracks."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import SpectralAnalysisWorker
        task = task_manager.create_task(f"Spectral: {title}", "8-Band Spektralanalyse")
        worker = SpectralAnalysisWorker(track_id, file_path)
        worker.task_id = task.task_id

        self.window.btn_spectral_analyze.setEnabled(False)
        self.window.btn_spectral_analyze.setText("Spektral laeuft...")
        self.window.progress_bar.setVisible(True)

        worker.progress.connect(
            lambda pct, msg: (
                self.window.progress_bar.setValue(int(pct)),
                self.window.progress_bar.setFormat(f"Spektral: %p%% — {msg[:50]}"),
                self.window._console_append(f"[Spectral] {msg}")
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, res: (
                self.window._console_append(f"[Spectral] Dominant: {res.get('dominant_band', '?')}"),
                self.window.media_table_controller._refresh_media_table_debounced(),
                self.window.btn_spectral_analyze.setEnabled(True),
                self.window.btn_spectral_analyze.setText("Spektral"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: (
                self.window._console_append(f"[Spectral] Fehler: {err}"),
                self.window.btn_spectral_analyze.setEnabled(True),
                self.window.btn_spectral_analyze.setText("Spektral"),
                self.window.progress_bar.setVisible(False),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)
        self.window.console_text.append(f"[Spectral] Starte Spektralanalyse fuer '{title}'...")

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

    def _create_classify_worker(self, track_id: int, file_path: str, bpm: float):
        from workers.audio_analysis import AudioClassifyWorker
        return AudioClassifyWorker(track_id, file_path, bpm=bpm)

    def _create_spectral_worker(self, track_id: int, file_path: str):
        from workers.audio_analysis import SpectralAnalysisWorker
        return SpectralAnalysisWorker(track_id, file_path)

    def _create_structure_worker(self, track_id: int, file_path: str, bpm: float):
        from workers.audio_analysis import StructureDetectionWorker
        return StructureDetectionWorker(track_id, file_path, bpm=bpm)

    def _create_stem_worker(self, track_id: int):
        from workers import StemSeparationWorker
        return StemSeparationWorker(track_id)
