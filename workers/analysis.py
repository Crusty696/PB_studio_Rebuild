"""Audio analysis background workers."""

import gc
import logging
import traceback

from PySide6.QtCore import QObject, Signal

from services.audio_service import AudioAnalyzer
from .base import CancellableMixin, format_user_error

logger = logging.getLogger(__name__)


class AnalysisWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)
    progress = Signal(int, str)

    def __init__(self, track_id: int, title: str):
        super().__init__()
        self.track_id = track_id
        self.title = title
        self.analyzer = AudioAnalyzer()

    def run(self):
        _ok = False
        self.started.emit(self.track_id, self.title)
        try:
            # Phase 1: Metadaten lesen (Dauer, Frequenzenergie via librosa STFT)
            self.progress.emit(10, "Lese Metadaten (Dauer, Energie)...")
            result = self.analyzer.analyze_and_store(self.track_id)

            # Phase 2: KI Beat-Analyse (Beatgrid mit Downbeats via beat_this)
            # BeatAnalysisService ist der alleinige Beatgrid-Writer.
            if not self.should_stop():
                try:
                    self.progress.emit(50, "Starte KI Beat-Analyse (beat_this)...")
                    from services.beat_analysis_service import BeatAnalysisService
                    beat_svc = BeatAnalysisService()
                    beat_result = beat_svc.analyze_and_store(self.track_id)
                    result["beat_positions"] = beat_result.get("beats", [])
                    result["downbeats"] = beat_result.get("downbeats", [])
                    self.progress.emit(90, "Beat-Analyse fertig")
                except Exception as e:
                    # Beat-Analyse ist optional — Grundanalyse reicht für den Betrieb
                    logging.warning("BeatAnalysis optional fehlgeschlagen: %s", e)
                    self.progress.emit(90, f"Beat-Analyse übersprungen: {e}")

            self.progress.emit(100, "Analyse komplett")
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("AnalysisWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.track_id, {})


class WaveformAnalysisWorker(QObject, CancellableMixin):
    """Background Worker: Rekordbox-Style Frequenzanalyse + Beatgrid."""
    finished = Signal(int, dict)   # track_id, result
    error = Signal(int, str)       # track_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import FrequencyAnalyzer
            analyzer = FrequencyAnalyzer()
            result = analyzer.analyze_and_store(
                self.track_id,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("WaveformAnalysisWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.track_id, {})
