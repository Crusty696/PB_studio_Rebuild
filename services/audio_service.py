import json
import threading
import numpy as np
import librosa

from sqlalchemy.orm import Session
from database import engine, AudioTrack
from services.audio_constants import DEFAULT_SR

# Per-Track Lock um Race Conditions bei parallelen Analysen desselben Tracks zu verhindern
_track_locks: dict[int, threading.Lock] = {}
_track_locks_guard = threading.Lock()


def _get_track_lock(track_id: int) -> threading.Lock:
    """Gibt einen Lock fuer den gegebenen Track zurueck (lazy erstellt)."""
    with _track_locks_guard:
        if track_id not in _track_locks:
            _track_locks[track_id] = threading.Lock()
        return _track_locks[track_id]


class AudioAnalyzer:
    """Analysiert Audiodateien: BPM-Erkennung, Beat-Positionen und Energiekurve (RMS)."""

    def __init__(self, sr: int = DEFAULT_SR):
        self.sr = sr

    @staticmethod
    def _tempo_to_float(tempo) -> float:
        """Robust conversion: librosa >=0.10 returns ndarray, older returns scalar."""
        if hasattr(tempo, '__len__') and len(tempo) == 0:
            return 0.0
        if isinstance(tempo, np.ndarray):
            return float(tempo.flat[0])
        return float(tempo)

    def analyze(self, file_path: str, progress_cb=None) -> dict:
        """Lädt Audio, berechnet BPM, Beat-Positionen + RMS-Energiekurve."""
        try:
            if progress_cb:
                progress_cb(0, "Lade Audio...")
            y, sr = librosa.load(file_path, sr=self.sr, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)

            if progress_cb:
                progress_cb(30, "Erkenne Beats...")
            # BPM + Beat-Frames
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm = round(self._tempo_to_float(tempo), 1)

            # Beat-Zeitpunkte in Sekunden
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            beat_positions = [round(float(t), 3) for t in beat_times]

            if progress_cb:
                progress_cb(70, "Berechne Energiekurve...")
            # RMS-Energiekurve (1 Wert pro Sekunde)
            hop_length = sr
            rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
            energy_curve = [round(float(v), 4) for v in rms]

            if progress_cb:
                progress_cb(100, "Fertig")

            return {
                "bpm": bpm,
                "duration": round(duration, 2),
                "sample_rate": sr,
                "energy_curve": energy_curve,
                "beat_positions": beat_positions,
            }
        except Exception as e:
            raise RuntimeError(f"Audio-Analyse fehlgeschlagen für {file_path}: {e}") from e

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und schreibt BPM, Duration, Energy in die DB.

        Beatgrid wird separat von BeatAnalysisService geschrieben.
        Session-Split: DB wird NICHT während der librosa-Analyse blockiert.
        Per-Track Lock verhindert Race Conditions bei parallelen Aufrufen.
        """
        lock = _get_track_lock(track_id)
        with lock:
            return self._analyze_and_store_locked(track_id, progress_cb)

    def _analyze_and_store_locked(self, track_id: int, progress_cb=None) -> dict:
        """Interne Implementierung von analyze_and_store (unter Lock)."""
        # 1) Erste Session: nur file_path laden, dann Session schließen
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        # 2) CPU-intensive Analyse AUSSERHALB jeder DB-Session
        result = self.analyze(file_path, progress_cb=progress_cb)

        # 3) Zweite Session: Ergebnisse speichern + commit
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nach Analyse nicht mehr gefunden")

            track.bpm = result["bpm"]
            track.duration = result["duration"]
            track.sample_rate = result["sample_rate"]
            track.energy_curve = json.dumps(result["energy_curve"])

            session.commit()

            try:
                from services.pacing_service import invalidate_pacing_caches
                invalidate_pacing_caches()
            except Exception:
                pass

        return result
