"""StemsController — Refactored from StemsMixin."""

import logging
from types import SimpleNamespace
from pathlib import Path
from PySide6.QtCore import Qt
from database import engine, AudioTrack
from sqlalchemy.orm import Session as DBSession
from services.task_manager import TaskManagerProxy
from workers import StemSeparationWorker, AutoDuckingWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

# B-110 / BUG-13-b: mirror the L-38 fix in video_analysis.py — lazy
# initialisation. A module-level ``task_manager = TaskManagerProxy()``
# breaks any importer that runs before QApplication exists (unit tests,
# CLI tools, alembic env). The proxy is created on first access.
_task_manager = None


def _get_task_manager() -> TaskManagerProxy:
    """Lazy TaskManagerProxy singleton."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManagerProxy()
    return _task_manager


# Backwards-compatible alias used throughout this controller. Resolves
# the lazy proxy on every attribute access via __getattr__-style facade.
class _TaskManagerFacade:
    def __getattr__(self, name):  # type: ignore[no-untyped-def]
        return getattr(_get_task_manager(), name)


task_manager = _TaskManagerFacade()

class StemsController(PBComponent):
    """Stem separation and auto-ducking methods for PBWindow."""

    def _on_stem_playback_finished(self):
        if hasattr(self.window, "stem_workspace"):
            self.window.stem_workspace.update_position(0.0)
        if hasattr(self.window, "_schnitt_audio_binder"):
            self.window._schnitt_audio_binder.update_position(0.0)

    def _update_stem_workspace(self, track_id: int):
        """Lädt Stem-Pfade aus der DB, aktualisiert StemWorkspace und Player."""
        try:
            with DBSession(engine) as session:
                track_row = (
                    session.query(
                        AudioTrack.id,
                        AudioTrack.title,
                        AudioTrack.duration,
                        AudioTrack.energy_curve,
                        AudioTrack.stem_vocals_path,
                        AudioTrack.stem_drums_path,
                        AudioTrack.stem_bass_path,
                        AudioTrack.stem_other_path,
                    )
                    .filter(AudioTrack.id == track_id)
                    .first()
                )
                if not track_row:
                    if hasattr(self.window, "stem_workspace"):
                        self.window.stem_workspace.update_for_track(None, None)
                    if hasattr(self.window, "_schnitt_audio_binder"):
                        self.window._schnitt_audio_binder.update_stems(None, None)
                        self.window._schnitt_audio_binder.set_duration(0.0)
                    if hasattr(self.window, "_stems_ws"):
                        self.window._stems_ws.update_analysis(None)
                    self.window.stem_player.stop()
                    return
                stem_paths = {
                    "vocals": track_row.stem_vocals_path,
                    "drums": track_row.stem_drums_path,
                    "bass": track_row.stem_bass_path,
                    "other": track_row.stem_other_path,
                }
                loaded = self.window.stem_player.load_stems(stem_paths)
                if hasattr(self.window, "stem_workspace"):
                    self.window.stem_workspace.update_for_track(track_id, stem_paths)
                    if loaded:
                        self.window.stem_workspace.set_duration(self.window.stem_player.duration)
                    else:
                        self.window.stem_workspace.set_duration(0.0)
                if hasattr(self.window, "_schnitt_audio_binder"):
                    self.window._schnitt_audio_binder.update_stems(track_id, stem_paths)
                    if loaded:
                        self.window._schnitt_audio_binder.set_duration(self.window.stem_player.duration)
                    else:
                        self.window._schnitt_audio_binder.set_duration(0.0)
                if hasattr(self.window, "_stems_ws"):
                    self.window._stems_ws.update_analysis(
                        SimpleNamespace(
                            id=track_row.id,
                            title=track_row.title,
                            duration=track_row.duration,
                            energy_curve=track_row.energy_curve,
                        )
                    )
                if loaded:
                    self.window.console_text.append(f"[StemPlayer] Track #{track_id} geladen: {self.window.stem_player.duration:.1f}s")
        except Exception as e:
            logger.error("[StemWorkspace] Error: %s", e, exc_info=True)
            self.window.console_text.append(f"[Stem-Widget] Fehler: {e}")

    def _start_stem_separation(self):
        # B-293 Phase B: Stems bleibt Single-Track. Demucs braucht 5+ min/Track,
        # Batch-Decision deferred (User-Frage steht aus). Single-Helper ist
        # bereits checkbox-aware (Phase A): erstes gechecktes ODER Maus-Selection.
        info = self.window.audio_analysis._get_selected_audio_track()
        if not info:
            return
        track_id, _, title, _ = info
        task = task_manager.create_task(f"Stems: {title}", "KI Stem Separation (Demucs)")
        self.window.btn_stem_separate.setEnabled(False)
        self.window.btn_stem_separate.setText("Stems laeuft...")
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(0)
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setFormat("KI-Stems: %p%% — Initialisierung...")
        self.window.console_text.append(f"[Stems] Starte KI-Stem-Separation fuer '{title}'...")

        worker = StemSeparationWorker(track_id)
        worker.task_id = task.task_id
        # Bug C: Buffered append statt synchronem QTextEdit.append() pro Tick.
        worker.progress.connect(
            self._on_stem_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda tid, r: self._on_stem_finished(tid, r, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda tid, err: self._on_stem_error(tid, err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker, on_error=lambda *_args: None)

    def _on_stem_progress(self, pct: int, msg: str):
        """B-290: Demucs-Progress an progress_bar binden."""
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        self.window.progress_bar.setFormat(f"KI-Stems: %p%% — {msg[:50]}")
        self.window._console_append(f"[Stems] {msg} ({pct}%)")

    def _on_stem_finished(self, track_id: int, stems: dict, task_id: str):
        self.window.btn_stem_separate.setEnabled(True)
        self.window.btn_stem_separate.setText("Stems")
        self.window.progress_bar.setVisible(False)
        if not stems:
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        stem_list = [f"{k}: {('OK' if v else 'fehlt')}" for k, v in stems.items()]
        self.window.console_text.append(f"[Stems] Separation fertig: {', '.join(stem_list)}")
        self.window.media_table_controller._refresh_media_table()
        self._update_stem_workspace(track_id)
        task_manager.finish_task(task_id, "finished", "Stems OK")

    def _on_stem_error(self, track_id: int, error_msg: str, task_id: str):
        self.window.btn_stem_separate.setEnabled(True)
        self.window.btn_stem_separate.setText("Stems")
        self.window.progress_bar.setVisible(False)
        if "abgebrochen" in error_msg.lower() or "cancel" in error_msg.lower():
            self.window.console_text.append(f"[Stems] {error_msg}")
            task_manager.finish_task(task_id, "cancelled", error_msg)
            return
        self.window.console_text.append(f"[Stem-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    def _start_auto_ducking(self):
        info = self.window.audio_analysis._get_selected_audio_track()
        if not info:
            return
        track_id = info[0]
        with DBSession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if not track or not track.stem_vocals_path or not track.stem_other_path:
                self.window.console_text.append("[Ducking] Zuerst Stems separieren!")
                return
            vocals_path = track.stem_vocals_path
            other_path = track.stem_other_path
            title = track.title

        import re
        ducked_dir = Path(__file__).parent.parent.parent / "storage" / "ducked"
        ducked_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title or "track")
        output_path = str(ducked_dir / f"{safe_title}_ducked.wav")
        task = task_manager.create_task(f"Ducking: {title}", "Auto-Ducking")
        self.window.btn_auto_duck.setEnabled(False)
        self.window.btn_auto_duck.setText("Ducking laeuft...")
        self.window.console_text.append(f"[Ducking] Starte Auto-Ducking fuer '{title}'...")

        worker = AutoDuckingWorker(other_path, vocals_path, output_path)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda p: self._on_ducking_finished(p, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda err: self._on_ducking_error(err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_ducking_finished(self, output_path: str, task_id: str):
        self.window.btn_auto_duck.setEnabled(True)
        self.window.btn_auto_duck.setText("Auto-Ducking")
        if not output_path:
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.window.console_text.append(f"[Ducking] Fertig: {output_path}")
        task_manager.finish_task(task_id, "finished", f"Gespeichert: {output_path}")

    def _on_ducking_error(self, error_msg: str, task_id: str):
        self.window.btn_auto_duck.setEnabled(True)
        self.window.btn_auto_duck.setText("Auto-Ducking")
        self.window.console_text.append(f"[Ducking-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)
