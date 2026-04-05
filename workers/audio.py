"""AI audio processing background workers (stem separation, ducking)."""

import gc
import logging
import traceback

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin, format_user_error

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
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("StemSeparationWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, format_user_error(e))
        finally:
            # VRAM-Schutz: GPU-Speicher nach Demucs freigeben (6GB Limit)
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError as e:
                logger.warning("torch not available for VRAM cleanup after stem separation: %s", e)
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
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("AutoDuckingWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit("")


class TranscriptionWorker(QObject, CancellableMixin):
    """Background-Worker fuer Audio-Transkription via faster-whisper."""
    finished = Signal(int, dict)   # track_id, {"text": ..., "language": ..., "segments": [...]}
    error = Signal(int, str)       # track_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, track_id: int, language: str | None = None):
        super().__init__()
        self.track_id = track_id
        self.language = language

    def run(self):
        _ok = False
        try:
            from services.transcription_service import TranscriptionService
            svc = TranscriptionService()
            result = svc.transcribe_and_store(
                self.track_id,
                language=self.language,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.track_id, {
                "text": result.text,
                "language": result.language,
                "language_probability": result.language_probability,
                "segments": result.segments,
                "duration": result.duration,
            })
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("TranscriptionWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, format_user_error(e))
        finally:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError as e:
                logger.warning("torch not available for VRAM cleanup after transcription: %s", e)
            gc.collect()
            if not _ok and not self._errored:
                self.finished.emit(self.track_id, {})
