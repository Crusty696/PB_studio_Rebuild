import json
import numpy as np
import librosa

from sqlalchemy.orm import Session
from database import engine, AudioTrack, Beatgrid


class AudioAnalyzer:
    """Analysiert Audiodateien: BPM-Erkennung, Beat-Positionen und Energiekurve (RMS)."""

    def __init__(self, sr: int = 22050):
        self.sr = sr

    @staticmethod
    def _tempo_to_float(tempo) -> float:
        """Robust conversion: librosa >=0.10 returns ndarray, older returns scalar."""
        if isinstance(tempo, np.ndarray):
            return float(tempo.flat[0])
        return float(tempo)

    def analyze(self, file_path: str) -> dict:
        """Lädt Audio, berechnet BPM, Beat-Positionen + RMS-Energiekurve."""
        y, sr = librosa.load(file_path, sr=self.sr, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # BPM + Beat-Frames
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        bpm = round(self._tempo_to_float(tempo), 1)

        # Beat-Zeitpunkte in Sekunden
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        beat_positions = [round(float(t), 3) for t in beat_times]

        # RMS-Energiekurve (1 Wert pro Sekunde)
        hop_length = sr
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        energy_curve = [round(float(v), 4) for v in rms]

        return {
            "bpm": bpm,
            "duration": round(duration, 2),
            "sample_rate": sr,
            "energy_curve": energy_curve,
            "beat_positions": beat_positions,
        }

    def analyze_and_store(self, track_id: int) -> dict:
        """Analysiert einen AudioTrack und schreibt Ergebnisse + Beatgrid in die DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")

            result = self.analyze(track.file_path)

            track.bpm = result["bpm"]
            track.duration = result["duration"]
            track.sample_rate = result["sample_rate"]
            track.energy_curve = json.dumps(result["energy_curve"])

            # Beatgrid speichern/aktualisieren
            if track.beatgrid:
                track.beatgrid.bpm = result["bpm"]
                track.beatgrid.beat_positions = json.dumps(result["beat_positions"])
            else:
                bg = Beatgrid(
                    audio_track_id=track_id,
                    bpm=result["bpm"],
                    offset=result["beat_positions"][0] if result["beat_positions"] else 0.0,
                    beat_positions=json.dumps(result["beat_positions"]),
                )
                session.add(bg)

            session.commit()

        return result
