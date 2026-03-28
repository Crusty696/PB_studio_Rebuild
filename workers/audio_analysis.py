"""Phase 4: Audio-Analyse Worker fuer Background-Processing.

Alle Worker erben von BaseAnalysisWorker, der das try/except/finally,
Signal-Emit und DB-Save Boilerplate kapselt. Jeder konkrete Worker
implementiert nur _analyze() und _save_to_db().
"""

import logging
import traceback
from abc import abstractmethod

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin, format_user_error

logger = logging.getLogger(__name__)


# ── Base Worker ──────────────────────────────────────────────────────────


class BaseAnalysisWorker(QObject, CancellableMixin):
    """Template-Basis fuer alle Audio-Analyse Worker.

    Subklassen implementieren:
        _start_message() -> str
        _analyze() -> object (Service-spezifisches Result)
        _done_message(result) -> str
        _save_to_db(result) -> None
        _result_to_dict(result) -> dict (fuer finished-Signal)
    """

    finished = Signal(int, dict)   # audio_track_id, result_dict
    error = Signal(int, str)       # audio_track_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, audio_track_id: int, file_path: str, **kwargs):
        super().__init__()
        CancellableMixin.__init__(self)
        self.audio_track_id = audio_track_id
        self.file_path = file_path

    def run(self) -> None:
        self._errored = False
        _ok = False
        try:
            self.progress.emit(10, self._start_message())
            result = self._analyze()
            self.progress.emit(80, self._done_message(result))
            self._save_to_db(result)
            self.progress.emit(100, "Fertig")
            self.finished.emit(self.audio_track_id, self._result_to_dict(result))
            _ok = True
        except Exception as e:
            logger.error(
                "%s[%s] crashed: %s\n%s",
                type(self).__name__, self.audio_track_id, e, traceback.format_exc(),
            )
            self._errored = True
            self.error.emit(self.audio_track_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.audio_track_id, {})

    @abstractmethod
    def _start_message(self) -> str: ...

    @abstractmethod
    def _analyze(self) -> object: ...

    @abstractmethod
    def _done_message(self, result) -> str: ...

    @abstractmethod
    def _save_to_db(self, result) -> None: ...

    @abstractmethod
    def _result_to_dict(self, result) -> dict: ...

    def _get_session_context(self):
        """Hilfsmethode: Gibt einen SQLAlchemy Session-Kontextmanager zurueck.

        Bug-B2 fix: Statt einer nackten Session (die bei fruehzeitiger Exception
        leaken kann) wird jetzt ein Context-Manager zurueckgegeben, der die
        Session immer sauber schliesst.

        Verwendung:
            with self._get_session_context() as session:
                track = session.get(AudioTrack, self.audio_track_id)
                ...
        """
        from database import engine
        from sqlalchemy.orm import Session
        return Session(engine)


# ── Konkrete Worker ──────────────────────────────────────────────────────


class KeyDetectionWorker(BaseAnalysisWorker):
    """Background-Worker fuer Key-Erkennung (Krumhansl-Kessler)."""

    def _start_message(self) -> str:
        return "Key-Erkennung gestartet..."

    def _analyze(self):
        from services.key_detection_service import KeyDetectionService
        return KeyDetectionService().detect_key(self.file_path)

    def _done_message(self, result) -> str:
        return f"Key erkannt: {result.key} ({result.camelot})"

    def _save_to_db(self, result) -> None:
        from database import AudioTrack
        with self._get_session_context() as session:
            track = session.get(AudioTrack, self.audio_track_id)
            if track:
                track.key = result.key
                track.key_confidence = result.confidence
                session.commit()

    def _result_to_dict(self, result) -> dict:
        return {
            "key": result.key,
            "camelot": result.camelot,
            "confidence": result.confidence,
            "is_minor": result.is_minor,
        }


class LUFSAnalysisWorker(BaseAnalysisWorker):
    """Background-Worker fuer LUFS-Lautstaerke-Analyse (EBU R128)."""

    def _start_message(self) -> str:
        return "LUFS-Analyse gestartet..."

    def _analyze(self):
        from services.lufs_service import LUFSService
        return LUFSService().analyze(self.file_path)

    def _done_message(self, result) -> str:
        return f"LUFS: {result.integrated:.1f} dB"

    def _save_to_db(self, result) -> None:
        from database import AudioTrack
        with self._get_session_context() as session:
            track = session.get(AudioTrack, self.audio_track_id)
            if track:
                track.lufs = result.integrated
                session.commit()

    def _result_to_dict(self, result) -> dict:
        return {
            "integrated": result.integrated,
            "short_term_max": result.short_term_max,
            "loudness_range": result.loudness_range,
            "true_peak": result.true_peak,
        }


class AudioClassifyWorker(BaseAnalysisWorker):
    """Background-Worker fuer Audio-Klassifikation (Mood, Genre, DJ-Mix)."""

    def __init__(self, audio_track_id: int, file_path: str, bpm: float | None = None):
        super().__init__(audio_track_id, file_path)
        self.bpm = bpm

    def _start_message(self) -> str:
        return "Audio-Klassifikation gestartet..."

    def _analyze(self):
        from services.audio_classify_service import AudioClassifyService
        return AudioClassifyService().classify(self.file_path, bpm=self.bpm)

    def _done_message(self, result) -> str:
        return f"Genre: {result.genre}, Mood: {result.mood}"

    def _save_to_db(self, result) -> None:
        from database import AudioTrack
        with self._get_session_context() as session:
            track = session.get(AudioTrack, self.audio_track_id)
            if track:
                track.mood = result.mood
                track.genre = result.genre
                track.is_dj_mix = result.is_dj_mix
                session.commit()

    def _result_to_dict(self, result) -> dict:
        return {
            "mood": result.mood,
            "genre": result.genre,
            "energy_level": result.energy_level,
            "is_dj_mix": result.is_dj_mix,
            "confidence": result.confidence,
            "description": result.description,
        }


class SpectralAnalysisWorker(BaseAnalysisWorker):
    """Background-Worker fuer 8-Band Spektral-Analyse."""

    def __init__(self, audio_track_id: int, file_path: str, **kwargs):
        super().__init__(audio_track_id, file_path, **kwargs)
        # Bug-B3 fix: initialize _svc to None so _save_to_db() can detect
        # that _analyze() has not been run yet, rather than raising AttributeError.
        self._svc = None

    def _start_message(self) -> str:
        return "Spektral-Analyse gestartet..."

    def _analyze(self):
        from services.spectral_analysis_service import SpectralAnalysisService
        self._svc = SpectralAnalysisService()
        return self._svc.analyze(self.file_path)

    def _done_message(self, result) -> str:
        return f"Dominant: {result.dominant_band}"

    def _save_to_db(self, result) -> None:
        if self._svc is None:
            raise RuntimeError(
                "SpectralAnalysisWorker._save_to_db() aufgerufen bevor _analyze() lief"
            )
        from database import AudioTrack
        bands_json = self._svc.get_bands_json(result)
        with self._get_session_context() as session:
            track = session.get(AudioTrack, self.audio_track_id)
            if track:
                track.spectral_bands = bands_json
                session.commit()

    def _result_to_dict(self, result) -> dict:
        return {
            "dominant_band": result.dominant_band,
            "spectral_centroid_mean": result.spectral_centroid_mean,
            "band_count": len(result.bands),
            "event_count": len(result.events),
        }


class StructureDetectionWorker(BaseAnalysisWorker):
    """Background-Worker fuer Song-Struktur-Erkennung."""

    def __init__(self, audio_track_id: int, file_path: str,
                 bpm: float | None = None,
                 beat_positions: list[float] | None = None,
                 energy_per_beat: list[float] | None = None):
        super().__init__(audio_track_id, file_path)
        self.bpm = bpm
        self.beat_positions = beat_positions
        self.energy_per_beat = energy_per_beat
        # Bug-B3 fix: initialize _svc to None so _save_to_db() can detect
        # that _analyze() has not been run yet.
        self._svc = None

    def _start_message(self) -> str:
        return "Struktur-Erkennung gestartet..."

    def _analyze(self):
        from services.structure_detection_service import StructureDetectionService
        self._svc = StructureDetectionService()
        return self._svc.detect(
            self.file_path,
            bpm=self.bpm,
            beat_positions=self.beat_positions,
            energy_per_beat=self.energy_per_beat,
        )

    def _done_message(self, result) -> str:
        return f"{len(result.segments)} Segmente erkannt"

    def _save_to_db(self, result) -> None:
        if self._svc is None:
            raise RuntimeError(
                "StructureDetectionWorker._save_to_db() aufgerufen bevor _analyze() lief"
            )
        self._svc.save_to_db(self.audio_track_id, result)

    def _result_to_dict(self, result) -> dict:
        return {
            "segment_count": len(result.segments),
            "is_dj_mix": result.is_dj_mix,
            "transition_count": result.transition_count,
            "segments": [
                {"label": s.label, "start": s.start_time, "end": s.end_time}
                for s in result.segments
            ],
        }
