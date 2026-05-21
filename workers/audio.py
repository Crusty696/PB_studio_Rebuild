"""AI audio processing background workers (stem separation, ducking)."""

import gc
import logging
import traceback

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin, format_user_error
from services.analysis_status_service import mark_started, mark_done, mark_error, mark_cancelled

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
            mark_started("audio", self.track_id, "stem_separation")
            from services.ai_audio_service import StemSeparator
            from services.model_manager import GPU_EXECUTION_LOCK
            separator = StemSeparator()

            # F-004 Fix: Inferenz-Phase global locken
            with GPU_EXECUTION_LOCK:
                result = separator.separate_and_store(
                    self.track_id,
                    progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                    should_stop=self.should_stop,
                )

            mark_done("audio", self.track_id, "stem_separation", {
                "stems": result.get("stem_count", 4),
            })
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            if "abgebrochen (User-Cancel)" in str(e):
                logger.info("StemSeparationWorker[%s] cancelled: %s", self.track_id, e)
                self._errored = True
                mark_cancelled("audio", self.track_id, "stem_separation")
                self.error.emit(self.track_id, "Stem-Separation abgebrochen (User-Cancel)")
                return
            logging.error("StemSeparationWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            mark_error("audio", self.track_id, "stem_separation", str(e))
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
            # B-074: should_stop durchreichen — Worker ist CancellableMixin,
            # daher ist self.should_stop verfuegbar. Damit reagiert Cancel
            # innerhalb von <5s auch waehrend der FFmpeg-Konvertierung.
            result = ducker.create_ducked_audio(
                self.music_path, self.voice_path, self.output_path,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                should_stop=self.should_stop,
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


