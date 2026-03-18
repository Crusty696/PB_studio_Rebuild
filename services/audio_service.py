import json
import numpy as np
import librosa

from sqlalchemy.orm import Session
from database import engine, AudioTrack


class AudioAnalyzer:
    """Analysiert Audiodateien: BPM-Erkennung und Energiekurve (RMS)."""

    def __init__(self, sr: int = 22050):
        self.sr = sr

    def analyze(self, file_path: str) -> dict:
        """Lädt Audio, berechnet BPM + RMS-Energiekurve."""
        y, sr = librosa.load(file_path, sr=self.sr, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.round(tempo, 1))

        # RMS-Energiekurve (1 Wert pro Sekunde)
        hop_length = sr  # 1 Frame = 1 Sekunde
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        energy_curve = [round(float(v), 4) for v in rms]

        return {
            "bpm": bpm,
            "duration": round(duration, 2),
            "sample_rate": sr,
            "energy_curve": energy_curve,
        }

    def analyze_and_store(self, track_id: int) -> dict:
        """Analysiert einen AudioTrack und schreibt Ergebnisse in die DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")

            result = self.analyze(track.file_path)

            track.bpm = result["bpm"]
            track.duration = result["duration"]
            track.sample_rate = result["sample_rate"]
            track.energy_curve = json.dumps(result["energy_curve"])
            session.commit()

        return result
