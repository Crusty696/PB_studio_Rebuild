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
            # GPU-ZWANG: beat_this MUSS auf CUDA laufen wenn verfügbar
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    def _ensure_model(self) -> None:
        """Laedt das beat_this Modell (lazy, einmalig).

        WICHTIG: Entlaedt zuerst den ModelManager, damit kein anderes
        Modell gleichzeitig VRAM belegt (GTX 1060 = 6GB Budget).
        """
        if self._model is not None:
            return
        # ModelManager entladen bevor beat_this GPU-Speicher beansprucht
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except Exception:
            pass
        from beat_this.inference import File2Beats
        import torch, gc
        if torch.cuda.is_available():
            logger.info("GPU-ZWANG: beat_this wird auf CUDA geladen (%s)", torch.cuda.get_device_name(0))
        logger.info("Lade beat_this Modell (device=%s, dbn=False)...", self.device)
        try:
            self._model = File2Beats(device=self.device, dbn=False)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            raise RuntimeError(
                f"VRAM reicht nicht fuer beat_this auf '{self.device}'. "
                "Bitte andere GPU-Modelle entladen."
            )
        logger.info("beat_this Modell geladen.")

    def unload(self) -> None:
        """Entlaedt das Modell und gibt VRAM frei."""
        if self._model is not None:
            import torch, gc
            # Model auf CPU verschieben bevor Referenz geloescht wird
            if hasattr(self._model, 'cpu'):
                try:
                    self._model.cpu()
                except Exception:
                    pass
            del self._model
            self._model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("beat_this Modell entladen, VRAM freigegeben.")

    def analyze(self, audio_path: str | Path, progress_cb=None) -> dict:
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

        if progress_cb:
            progress_cb(0, "Lade Audio...")

        # Dauer bestimmen
        duration = librosa.get_duration(path=audio_path)
        if duration < 0.5:
            raise ValueError(f"Audio-Datei zu kurz ({duration:.2f}s): {Path(audio_path).name}")
        logger.info("Audio-Dauer: %.1fs (%s)", duration, Path(audio_path).name)

        if progress_cb:
            progress_cb(10, "Lade beat_this Modell...")

        try:
            if duration <= CHUNK_DURATION_SEC:
                if progress_cb:
                    progress_cb(20, "Analysiere Beats...")
                # Kurze Datei: direkt analysieren
                beats, downbeats = self._analyze_full(audio_path)
            else:
                if progress_cb:
                    progress_cb(20, "Chunked Beat-Analyse...")
                # Lange Datei: Chunked Processing
                beats, downbeats = self._analyze_chunked(audio_path, duration)
        finally:
            # VRAM sofort freigeben nach Analyse (beat_this umgeht ModelManager)
            self.unload()

        if progress_cb:
            progress_cb(80, "Berechne BPM...")

        # BPM aus Beat-Intervallen berechnen
        bpm = 0.0
        if len(beats) > 1:
            intervals = np.diff(beats)
            median_interval = float(np.median(intervals))
            if median_interval > 0:
                bpm = round(60.0 / median_interval, 1)

        if progress_cb:
            progress_cb(100, "Fertig")

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
            if chunk_end >= total_samples:
                break
            pos = chunk_end - overlap_samples
            chunk_idx += 1

        return np.array(all_beats), np.array(all_downbeats)

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und speichert Beats/Downbeats in der DB.

        Aktualisiert den Beatgrid-Eintrag mit beat_this-Ergebnissen.
        Phase 3: Speichert auch Downbeats und Per-Beat-RMS-Energie.
        """
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        result = self.analyze(file_path, progress_cb=progress_cb)

        # Phase 3: Per-Beat RMS-Energie berechnen
        energy_per_beat = self._compute_energy_per_beat(
            file_path, result["beats"], result["duration"]
        )

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")

            track.bpm = result["bpm"]
            track.duration = result["duration"]

            # Beatgrid aktualisieren mit allen Beats + Downbeats + Energie
            beat_positions_json = json.dumps(result["beats"])
            downbeat_positions_json = json.dumps(result["downbeats"])
            energy_json = json.dumps(energy_per_beat)

            if track.beatgrid:
                track.beatgrid.bpm = result["bpm"]
                track.beatgrid.beat_positions = beat_positions_json
                track.beatgrid.downbeat_positions = downbeat_positions_json
                track.beatgrid.energy_per_beat = energy_json
                track.beatgrid.offset = result["beats"][0] if result["beats"] else 0.0
            else:
                bg = Beatgrid(
                    audio_track_id=track_id,
                    bpm=result["bpm"],
                    offset=result["beats"][0] if result["beats"] else 0.0,
                    beat_positions=beat_positions_json,
                    downbeat_positions=downbeat_positions_json,
                    energy_per_beat=energy_json,
                )
                session.add(bg)

            session.commit()

            try:
                from services.pacing_service import invalidate_pacing_caches
                invalidate_pacing_caches()
            except Exception:
                pass

        return result

    @staticmethod
    def _compute_energy_per_beat(
        audio_path: str, beats: list[float], duration: float
    ) -> list[float]:
        """Berechnet RMS-Energie pro Beat-Intervall (0.0 - 1.0 normalisiert)."""
        if not beats or len(beats) < 2:
            return []
        try:
            import librosa
            y, sr = librosa.load(audio_path, sr=22050, mono=True)
        except Exception as e:
            logger.warning("_compute_energy_per_beat: librosa.load fehlgeschlagen (%s), nutze 0.5 Fallback", e)
            return [0.5] * len(beats)

        # Vectorized: Beat-Grenzen als Sample-Indices berechnen
        beat_ends = list(beats[1:]) + [duration]
        starts = np.clip((np.array(beats) * 22050).astype(int), 0, len(y))
        ends = np.clip((np.array(beat_ends) * 22050).astype(int), 0, len(y))

        energies = np.zeros(len(beats), dtype=np.float64)
        for i in range(len(beats)):
            if ends[i] > starts[i]:
                seg = y[starts[i]:ends[i]]
                energies[i] = np.sqrt(np.mean(seg ** 2))

        # Normalisiere auf 0.0-1.0
        max_e = energies.max() if len(energies) else 1.0
        if max_e > 0:
            energies = energies / max_e
        return [round(float(e), 4) for e in energies]
