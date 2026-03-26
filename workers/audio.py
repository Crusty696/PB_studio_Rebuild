"""AI audio processing background workers (stem separation, ducking)."""

import gc
import logging
import traceback

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin

logger = logging.getLogger(__name__)


class StemSeparationWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    progress = Signal(int, str)

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import StemSeparator
            separator = StemSeparator()
            result = separator.separate_and_store(
                self.track_id,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("StemSeparationWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, str(e))
        finally:
            # VRAM-Schutz: GPU-Speicher nach Demucs freigeben (6GB Limit)
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            gc.collect()
            if not _ok and not self._errored:
                self.finished.emit(self.track_id, {})


class AutoDuckingWorker(QObject, CancellableMixin):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, music_path: str, voice_path: str, output_path: str):
        super().__init__()
        self.music_path = music_path
        self.voice_path = voice_path
        self.output_path = output_path

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import AutoDucker
            ducker = AutoDucker()
            result = ducker.create_ducked_audio(
                self.music_path, self.voice_path, self.output_path,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(result)
            _ok = True
        except Exception as e:
            logging.error("AutoDuckingWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit("")
