"""Beat-Analyse Service mit beat_this + Chunked Processing.

Phase 1 Foundation — SEKTOR 4.
PoC-Erkenntnis R4: GTX 1060 hat 6GB VRAM. Ein 60-Min-Mix braucht ~2.9GB.
ZWINGEND: Chunked Processing fuer lange Audio-Dateien.
dbn=False verhindert madmom-Abhaengigkeit.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from sqlalchemy.orm import Session
from database import engine, AudioTrack, Beatgrid

logger = logging.getLogger(__name__)

# Chunk-Groesse: 10 Minuten in Sekunden (PoC-validiert fuer 6GB VRAM)
CHUNK_DURATION_SEC = 600.0

# Overlap zwischen Chunks fuer saubere Beat-Uebergaenge (5 Sekunden)
CHUNK_OVERLAP_SEC = 5.0


class BeatAnalysisService:
    """GPU-beschleunigte Beat/Downbeat-Erkennung mit beat_this.

    Verwendet Chunked Processing um auch 60+ Minuten Mixes auf
    einer GTX 1060 (6GB VRAM) analysieren zu koennen.
    """

    def __init__(self, device: str | None = None):
        self._model = None
        self._device = device

    @property
    def device(self) -> str:
        if self._device is None:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    def _ensure_model(self) -> None:
        """Laedt das beat_this Modell (lazy, einmalig)."""
        if self._model is not None:
            return
        from beat_this.inference import File2Beats
        logger.info("Lade beat_this Modell (device=%s, dbn=False)...", self.device)
        self._model = File2Beats(device=self.device, dbn=False)
        logger.info("beat_this Modell geladen.")

    def unload(self) -> None:
        """Entlaedt das Modell und gibt VRAM frei."""
        if self._model is not None:
            del self._model
            self._model = None
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            logger.info("beat_this Modell entladen, VRAM freigegeben.")

    def analyze(self, audio_path: str | Path) -> dict:
        """Analysiert eine Audio-Datei und gibt Beats + Downbeats zurueck.

        Verwendet Chunked Processing fuer Dateien laenger als CHUNK_DURATION_SEC.

        Returns:
            {
                "beats": [float, ...],          # Beat-Zeitpunkte in Sekunden
                "downbeats": [float, ...],      # Downbeat-Zeitpunkte in Sekunden
                "bpm": float,                   # Geschaetztes BPM
                "duration": float,              # Audio-Dauer in Sekunden
                "num_beats": int,
                "num_downbeats": int,
            }
        """
        import librosa
        audio_path = str(audio_path)

        # Dauer bestimmen
        duration = librosa.get_duration(path=audio_path)
        logger.info("Audio-Dauer: %.1fs (%s)", duration, Path(audio_path).name)

        if duration <= CHUNK_DURATION_SEC:
            # Kurze Datei: direkt analysieren
            beats, downbeats = self._analyze_full(audio_path)
        else:
            # Lange Datei: Chunked Processing
            beats, downbeats = self._analyze_chunked(audio_path, duration)

        # BPM aus Beat-Intervallen berechnen
        bpm = 0.0
        if len(beats) > 1:
            intervals = np.diff(beats)
            median_interval = float(np.median(intervals))
            if median_interval > 0:
                bpm = round(60.0 / median_interval, 1)

        return {
            "beats": [round(float(b), 4) for b in beats],
            "downbeats": [round(float(b), 4) for b in downbeats],
            "bpm": bpm,
            "duration": round(duration, 2),
            "num_beats": len(beats),
            "num_downbeats": len(downbeats),
        }

    def _analyze_full(self, audio_path: str) -> tuple[np.ndarray, np.ndarray]:
        """Analysiert die komplette Datei in einem Durchgang."""
        self._ensure_model()
        beats, downbeats = self._model(audio_path)
        return np.array(beats), np.array(downbeats)

    def _analyze_chunked(
        self, audio_path: str, total_duration: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Chunked Processing: Teilt Audio in 10-Min-Segmente.

        1. Lade Audio in Chunks (mit Overlap)
        2. Analysiere jeden Chunk separat
        3. Setze Beat-Timestamps wieder zusammen (dedupliziere Overlap-Bereich)
        """
        import librosa
        import tempfile
        import soundfile as sf

        self._ensure_model()

        # Audio komplett laden (librosa cached, effizient)
        y, sr = librosa.load(audio_path, sr=22050, mono=True)

        chunk_samples = int(CHUNK_DURATION_SEC * sr)
        overlap_samples = int(CHUNK_OVERLAP_SEC * sr)
        total_samples = len(y)

        all_beats = []
        all_downbeats = []
        chunk_idx = 0
        pos = 0

        while pos < total_samples:
            chunk_end = min(pos + chunk_samples, total_samples)
            chunk_audio = y[pos:chunk_end]
            chunk_offset_sec = pos / sr

            logger.info(
                "Chunk %d: %.1fs - %.1fs (von %.1fs)",
                chunk_idx, chunk_offset_sec,
                chunk_end / sr, total_duration,
            )

            # Chunk als temporaere WAV speichern (beat_this erwartet Dateipfad)
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix=f"bt_chunk_{chunk_idx}_"
            ) as tmp:
                tmp_path = tmp.name
                sf.write(tmp_path, chunk_audio, sr)

            try:
                beats, downbeats = self._model(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            # Timestamps zum globalen Offset addieren
            beats = np.array(beats) + chunk_offset_sec
            downbeats = np.array(downbeats) + chunk_offset_sec

            # Overlap-Bereich: nur Beats akzeptieren die nach dem
            # letzten Beat des vorherigen Chunks liegen
            if all_beats and len(beats) > 0:
                last_beat = all_beats[-1]
                # Nur Beats behalten die mindestens 0.05s nach dem letzten sind
                mask = beats > (last_beat + 0.05)
                beats = beats[mask]
            if all_downbeats and len(downbeats) > 0:
                last_db = all_downbeats[-1]
                mask = downbeats > (last_db + 0.05)
                downbeats = downbeats[mask]

            all_beats.extend(beats.tolist())
            all_downbeats.extend(downbeats.tolist())

            # Naechster Chunk mit Overlap
            pos = chunk_end - overlap_samples
            if pos >= total_samples - overlap_samples:
                break
            chunk_idx += 1

        return np.array(all_beats), np.array(all_downbeats)

    def analyze_and_store(self, track_id: int) -> dict:
        """Analysiert einen AudioTrack und speichert Beats/Downbeats in der DB.

        Aktualisiert den Beatgrid-Eintrag mit beat_this-Ergebnissen.
        Speichert Downbeats als separate Metadata.
        """
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        result = self.analyze(file_path)

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")

            track.bpm = result["bpm"]
            track.duration = result["duration"]

            # Beatgrid aktualisieren mit allen Beats
            beat_positions_json = json.dumps(result["beats"])
            if track.beatgrid:
                track.beatgrid.bpm = result["bpm"]
                track.beatgrid.beat_positions = beat_positions_json
                track.beatgrid.offset = result["beats"][0] if result["beats"] else 0.0
            else:
                bg = Beatgrid(
                    audio_track_id=track_id,
                    bpm=result["bpm"],
                    offset=result["beats"][0] if result["beats"] else 0.0,
                    beat_positions=beat_positions_json,
                )
                session.add(bg)

            session.commit()

        return result
