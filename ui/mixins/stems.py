"""Stems Mixin fuer PBWindow."""

from pathlib import Path

from database import engine, AudioTrack
from sqlalchemy.orm import Session as DBSession

from services.task_manager import GlobalTaskManager

from workers import StemSeparationWorker, AutoDuckingWorker


# task_manager Proxy — gleiche Logik wie in main.py
class _TaskManagerProxy:
    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)

task_manager = _TaskManagerProxy()


class StemsMixin:
    """Stem separation and auto-ducking methods for PBWindow."""

    def _on_stem_playback_finished(self):
        """[I-10 FIX] Benannte Methode für playback_finished — reset Position."""
        if hasattr(self, "stem_workspace"):
            self.stem_workspace.update_position(0.0)

    def _update_stem_workspace(self, track_id: int):
        """Lädt Stem-Pfade aus der DB, aktualisiert StemWorkspace und Player."""
        try:
            with DBSession(engine) as session:
                track = session.query(AudioTrack).filter_by(id=track_id).first()
                if not track:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(None, None)
                    self.stem_player.stop()
                    return
                stem_paths = {
                    "vocals": track.stem_vocals_path,
                    "drums": track.stem_drums_path,
                    "bass": track.stem_bass_path,
                    "other": track.stem_other_path,
                }

                if self.stem_player.load_stems(stem_paths):
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
                        self.stem_workspace.set_duration(self.stem_player.duration)
                    self.console_text.append(
                        f"[StemPlayer] Track #{track_id} geladen: "
                        f"{self.stem_player.duration:.1f}s"
                    )
                else:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
                        self.stem_workspace.set_duration(0.0)
        except Exception as e:
            self.console_text.append(f"[Stem-Widget] Fehler: {e}")
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)

    def _start_stem_separation(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen separiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Stems: {title}", "KI Stem Separation (Demucs)")

        self.btn_stem_separate.setEnabled(False)
        self.btn_stem_separate.setText("Separation laeuft...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat("KI-Separation laeuft... (kann mehrere Minuten dauern)")

        self.console_text.append(f"[Stems] Starte KI-Stem-Separation fuer '{title}'...")

        worker = StemSeparationWorker(track_id)
        worker.task_id = task.task_id  # Verknuepfung mit bestehendem Task
        worker.progress.connect(
            lambda pct, msg: self.console_text.append(f"[Stems] {msg} ({pct}%)")
        )
        worker.finished.connect(lambda tid, r: self._on_stem_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_stem_error(tid, err, task.task_id))

        self._start_worker_thread(worker)

    def _on_stem_finished(self, track_id: int, stems: dict, task_id: str):
        if not stems:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_stem_separate.setEnabled(True)
            self.btn_stem_separate.setText("KI Stem Separation")
            self.progress_bar.setVisible(False)
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)

        stem_list = [f"{k}: {('OK' if v else 'fehlt')}" for k, v in stems.items()]
        self.console_text.append(f"[Stems] Separation fertig: {', '.join(stem_list)}")
        self._refresh_media_table()
        self._update_stem_workspace(track_id)
        task_manager.finish_task(task_id, "finished", "Stems OK")

    def _on_stem_error(self, track_id: int, error_msg: str, task_id: str):
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)
        self.console_text.append(f"[Stem-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    def _start_auto_ducking(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Waehle einen Audio-Track mit Stems.")
            return
        track_id = int(self.media_table.item(row, 0).text())

        with DBSession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if not track:
                return
            if not track.stem_vocals_path or not track.stem_other_path:
                self.console_text.append(
                    "[Ducking] Zuerst Stems separieren! (Vocals + Other benoetigt)"
                )
                return
            vocals_path = track.stem_vocals_path
            other_path = track.stem_other_path
            title = track.title

        import re as _re_ducking
        ducked_dir = Path(__file__).parent.parent.parent / "storage" / "ducked"
        ducked_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _re_ducking.sub(r'[<>:"/\\|?*]', '_', title or "track")
        output_path = str(ducked_dir / f"{safe_title}_ducked.wav")
        task = task_manager.create_task(f"Ducking: {title}", "Auto-Ducking")

        self.btn_auto_duck.setEnabled(False)
        self.btn_auto_duck.setText("Ducking laeuft...")

        self.console_text.append(f"[Ducking] Starte Auto-Ducking fuer '{title}'...")

        worker = AutoDuckingWorker(other_path, vocals_path, output_path)
        worker.task_id = task.task_id
        worker.finished.connect(lambda p: self._on_ducking_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_ducking_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_ducking_finished(self, output_path: str, task_id: str):
        if not output_path:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_auto_duck.setEnabled(True)
            self.btn_auto_duck.setText("Auto-Ducking")
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking] Fertig: {output_path}")
        task_manager.finish_task(task_id, "finished", f"Gespeichert: {output_path}")

    def _on_ducking_error(self, error_msg: str, task_id: str):
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)
