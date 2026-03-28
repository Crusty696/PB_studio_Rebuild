"""AI Audio Service: Demucs Stem Separation + Auto-Ducking + Rekordbox Frequency Analysis."""

import gc
import json
import logging
import subprocess
import sys
from pathlib import Path

import numpy as np
import librosa
from scipy.io import wavfile

# torch/torchaudio werden lazy importiert (nur in StemSeparator benötigt)
# damit das Modul auch ohne CUDA-Installation importierbar ist
try:
    import torch as _torch_module
    import torchaudio as _torchaudio_module
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
from sqlalchemy.orm import Session

from database import engine, AudioTrack, WaveformData, APP_ROOT

logger = logging.getLogger(__name__)

STEMS_DIR = APP_ROOT / "storage" / "stems"


def _sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages — strip full paths."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)

# Chunk-Dauer in Sekunden fuer VRAM-schonendes Processing
CHUNK_SECONDS = 30
# Overlap in Sekunden um Artefakte an Chunk-Grenzen zu vermeiden
OVERLAP_SECONDS = 2


class StemSeparator:
    """Trennt Audio via Demucs Python API in Vocals, Drums, Bass, Other.

    Verwendet Chunking (30s Bloecke) und erzwingt CUDA um VRAM-Limits
    (z.B. GTX 1060 6GB) einzuhalten und CPU-Fallback zu vermeiden.
    """

    def separate(self, file_path: str, model: str = "htdemucs_ft",
                 progress_cb=None) -> dict[str, str]:
        """Fuehrt Demucs Stem Separation mit Chunking + CUDA-Zwang aus.

        Returns: dict mit Keys 'vocals', 'drums', 'bass', 'other' -> Pfade.
        """
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "Stem-Separation erfordert PyTorch (torch). "
                "Bitte installieren: pip install torch torchaudio"
            )
        # Lokale Aliase für torch/torchaudio (lazy import oben definiert)
        import torch  # noqa: F811 — überschreibt lokalen Scope bewusst
        import torchaudio  # noqa: F811

        STEMS_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(file_path)

        # ── 1. VRAM freigeben: alle anderen Modelle entladen ──
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except Exception as e:
            logger.warning("ModelManager.unload() vor Demucs fehlgeschlagen: %s", e)
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # ── 2. Device bestimmen (CUDA erzwingen) ──
        if torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info(f"[StemSeparator] GPU erkannt: {torch.cuda.get_device_name(0)} "
                  f"({torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB VRAM)")
        else:
            raise RuntimeError(
                "Stem-Separation erfordert eine CUDA-faehige GPU (NVIDIA). "
                "Keine GPU erkannt — Abbruch.\n"
                "Loesung: NVIDIA-Treiber installieren und PyTorch CUDA-Version verwenden:\n"
                "  poetry run pip install torch==2.5.1+cu121 "
                "--index-url https://download.pytorch.org/whl/cu121"
            )

        if progress_cb:
            progress_cb(5, "Lade Demucs-Modell...")

        # ── 3. Demucs-Modell laden (Python API) ──
        from demucs.pretrained import get_model
        from demucs.apply import apply_model
        demucs_model = get_model(model)
        try:
            demucs_model.to(device)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            raise RuntimeError(
                f"VRAM reicht nicht fuer Demucs '{model}'. "
                "Bitte andere GPU-Modelle entladen oder kleineren Chunk verwenden."
            )
        demucs_model.eval()
        logger.info(f"[StemSeparator] Modell '{model}' geladen auf {device}")

        if progress_cb:
            progress_cb(10, "Lade Audio-Datei...")

        # ── 4. Audio laden ──
        waveform, sr = torchaudio.load(str(src))
        # Demucs erwartet die Samplerate des Modells
        model_sr = demucs_model.samplerate
        if sr != model_sr:
            waveform = torchaudio.functional.resample(waveform, sr, model_sr)
            sr = model_sr

        # Stereo sicherstellen (Demucs erwartet 2 Kanaele)
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        elif waveform.shape[0] > 2:
            waveform = waveform[:2]

        total_samples = waveform.shape[1]
        chunk_samples = CHUNK_SECONDS * sr
        overlap_samples = OVERLAP_SECONDS * sr
        step_samples = chunk_samples - overlap_samples

        # Berechne Chunk-Anzahl
        if total_samples <= chunk_samples:
            num_chunks = 1
        else:
            num_chunks = 1 + int(np.ceil((total_samples - chunk_samples) / step_samples))

        logger.info(f"[StemSeparator] Audio: {total_samples / sr:.1f}s, "
              f"SR={sr}, Chunks={num_chunks} (je {CHUNK_SECONDS}s, {OVERLAP_SECONDS}s Overlap)")

        if progress_cb:
            progress_cb(15, f"Starte Stem-Trennung in {num_chunks} Chunks...")

        # ── 5. Chunk-weise verarbeiten ──
        # Demucs Source-Namen ermitteln
        source_names = demucs_model.sources  # z.B. ['drums', 'bass', 'other', 'vocals']
        num_sources = len(source_names)

        # F-011: RAM-Budget pruefen — result_stems + weight_sum koennen bei
        # langen Mixes >5GB RAM belegen. Warnung und float16 bei >30min.
        estimated_ram_gb = (num_sources * waveform.shape[0] * total_samples * 4) / (1024**3)
        # A-11 Fix: VRAM-Budget zusaetzlich pruefen (GTX 1060 = 6GB)
        if torch.cuda.is_available():
            vram_free_gb = (torch.cuda.get_device_properties(0).total_memory
                            - torch.cuda.memory_reserved(0)) / (1024**3)
            if vram_free_gb < 2.0:
                logger.warning(
                    "[StemSeparator] Nur %.1f GB VRAM frei — reduziere Chunk-Groesse.",
                    vram_free_gb,
                )
        if estimated_ram_gb > 3.0:
            logger.warning(
                "[StemSeparator] Grosser Akkumulator: %.1f GB RAM geschaetzt fuer %.0f min Audio. "
                "Nutze float16 um Speicher zu halbieren.",
                estimated_ram_gb, total_samples / sr / 60,
            )
            accum_dtype = torch.float16
        else:
            accum_dtype = torch.float32

        # Ergebnis-Tensor fuer alle Stems (Crossfade-Akkumulator)
        result_stems = torch.zeros(num_sources, waveform.shape[0], total_samples, dtype=accum_dtype)
        weight_sum = torch.zeros(1, total_samples, dtype=accum_dtype)

        for i in range(num_chunks):
            start = i * step_samples
            end = min(start + chunk_samples, total_samples)
            chunk = waveform[:, start:end]

            logger.info(f"[StemSeparator] Verarbeite Chunk {i + 1}/{num_chunks} "
                  f"auf {device.type.upper()} "
                  f"({start / sr:.1f}s - {end / sr:.1f}s)...")

            # Chunk auf GPU, Batch-Dimension hinzufuegen: (1, channels, samples)
            chunk_gpu = chunk.unsqueeze(0).to(device)

            with torch.no_grad():
                # apply_model gibt (1, sources, channels, samples) zurueck
                estimates = apply_model(
                    demucs_model, chunk_gpu,
                    overlap=0.25,       # internes Demucs-Overlap fuer Qualitaet
                    progress=False,
                )

            # Zurueck auf CPU
            estimates_cpu = estimates.squeeze(0).cpu()  # (sources, channels, samples)

            # Crossfade-Gewicht: Dreiecks-Fenster fuer Overlap-Bereiche
            chunk_len = end - start
            fade = torch.ones(chunk_len)
            if i > 0 and overlap_samples > 0:
                # Fade-In am Anfang des Chunks (Overlap-Region)
                fade_len = min(overlap_samples, chunk_len)
                fade[:fade_len] = torch.linspace(0, 1, fade_len)
            if i < num_chunks - 1 and overlap_samples > 0:
                # Fade-Out am Ende des Chunks (Overlap-Region)
                fade_len = min(overlap_samples, chunk_len)
                fade[-fade_len:] = torch.linspace(1, 0, fade_len)

            # Gewichtete Addition (cast to accumulator dtype for float16 mode)
            for s in range(num_sources):
                weighted = (estimates_cpu[s, :, :chunk_len] * fade.unsqueeze(0)).to(accum_dtype)
                result_stems[s, :, start:end] += weighted
            weight_sum[0, start:end] += fade.to(accum_dtype)

            # ── VRAM sofort freigeben ──
            del chunk_gpu, estimates, estimates_cpu
            gc.collect()
            torch.cuda.empty_cache()

            # Progress: 15% bis 85% fuer Chunk-Processing
            if progress_cb:
                pct = 15 + int(70 * (i + 1) / num_chunks)
                progress_cb(pct, f"Chunk {i + 1}/{num_chunks} fertig")

        # Normalisierung durch Gewichtssumme (Crossfade)
        weight_sum = weight_sum.clamp(min=1e-8)
        for s in range(num_sources):
            result_stems[s] /= weight_sum

        # ── 6. Modell entladen ──
        del demucs_model
        gc.collect()
        torch.cuda.empty_cache()
        logger.info("[StemSeparator] Modell entladen, VRAM freigegeben")

        if progress_cb:
            progress_cb(90, "Speichere Stems als WAV...")

        # ── 7. Stems als WAV speichern ──
        stem_dir = STEMS_DIR / model / src.stem
        stem_dir.mkdir(parents=True, exist_ok=True)

        # Konvertiere zurueck zu float32 fuer WAV-Export (torchaudio erwartet float32)
        if result_stems.dtype != torch.float32:
            result_stems = result_stems.float()

        stems = {}
        for idx, stem_name in enumerate(source_names):
            stem_path = stem_dir / f"{stem_name}.wav"
            torchaudio.save(str(stem_path), result_stems[idx], sr)
            stems[stem_name] = str(stem_path.resolve())
            logger.info(f"[StemSeparator] Gespeichert: {stem_name} -> {stem_path}")

        # CPU-RAM freigeben: result_stems + weight_sum können >5GB sein bei langen Mixes
        del result_stems, weight_sum
        gc.collect()

        if progress_cb:
            progress_cb(100, "Stem Separation abgeschlossen")

        return stems

    def separate_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Separiert Stems und speichert Pfade in der DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        try:
            stems = self.separate(file_path, progress_cb=progress_cb)
        except Exception as e:
            raise RuntimeError(f"Stem-Separation fehlgeschlagen fuer Track {track_id}: {e}") from e

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nach Separation nicht mehr gefunden")
            track.stem_vocals_path = stems.get("vocals")
            track.stem_drums_path = stems.get("drums")
            track.stem_bass_path = stems.get("bass")
            track.stem_other_path = stems.get("other")
            session.commit()

        return stems


class AutoDucker:
    """Senkt Musik automatisch ab wenn Sprache erkannt wird."""

    def __init__(self, duck_db: float = -12.0, attack_ms: float = 200.0,
                 release_ms: float = 500.0, threshold_rms: float = 0.02):
        self.duck_db = duck_db
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.threshold_rms = threshold_rms

    def create_ducked_audio(self, music_path: str, voice_path: str,
                            output_path: str, progress_cb=None) -> str:
        """Erstellt eine geduckte Version: Musik wird leiser wenn Voice aktiv.

        Versucht FFmpeg, faellt auf Scipy zurueck bei Fehler.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(10, "Berechne Auto-Ducking...")

        # Erst: Konvertiere Inputs zu WAV falls noetig
        tmp_music = out.parent / "_tmp_music.wav"
        tmp_voice = out.parent / "_tmp_voice.wav"
        try:
            for src, dst in [(music_path, str(tmp_music)), (voice_path, str(tmp_voice))]:
                cmd = ["ffmpeg", "-y", "-i", src, "-ar", "44100", "-ac", "1",
                       "-c:a", "pcm_s16le", str(dst)]
                result = subprocess.run(
                    cmd, capture_output=True, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                if result.returncode != 0:
                    stderr_msg = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else (result.stderr or "")
                    raise RuntimeError(f"FFmpeg Konvertierung fehlgeschlagen: {_sanitize_ffmpeg_error(stderr_msg)}")

            if progress_cb:
                progress_cb(50, "Scipy Ducking laeuft...")

            result = self.create_ducked_audio_scipy(
                str(tmp_music), str(tmp_voice), output_path, progress_cb=None
            )

            if progress_cb:
                progress_cb(100, "Auto-Ducking fertig")

            return result
        finally:
            tmp_music.unlink(missing_ok=True)
            tmp_voice.unlink(missing_ok=True)

    def create_ducked_audio_scipy(self, music_path: str, voice_path: str,
                                   output_path: str, progress_cb=None) -> str:
        """Fallback: Scipy-basiertes Ducking wenn FFmpeg sidechaincompress fehlt."""
        if progress_cb:
            progress_cb(10, "Lade Audio-Dateien...")

        # WAV einlesen (fuer Stems die bereits WAV sind)
        music_sr, music_data = wavfile.read(music_path)
        voice_sr, voice_data = wavfile.read(voice_path)

        # Zu float32 normalisieren
        if music_data.dtype == np.int16:
            music_data = music_data.astype(np.float32) / 32768.0
        if voice_data.dtype == np.int16:
            voice_data = voice_data.astype(np.float32) / 32768.0

        # Mono sicherstellen
        if music_data.ndim > 1:
            music_data = music_data.mean(axis=1)
        if voice_data.ndim > 1:
            voice_data = voice_data.mean(axis=1)

        if progress_cb:
            progress_cb(30, "Berechne Voice-Envelope...")

        # Laengen anpassen
        min_len = min(len(music_data), len(voice_data))
        music_data = music_data[:min_len]
        voice_data = voice_data[:min_len]

        # Voice RMS Envelope berechnen (Fenster: 50ms) — vektorisiert
        window_size = int(music_sr * 0.05)
        from scipy.ndimage import uniform_filter1d
        envelope = np.sqrt(uniform_filter1d(voice_data.astype(np.float64) ** 2, size=window_size))

        if progress_cb:
            progress_cb(60, "Wende Ducking an...")

        # Ducking: Wo Voice laut ist, Musik leiser
        duck_factor = 10 ** (self.duck_db / 20.0)  # z.B. -12dB -> 0.25
        gain = np.where(envelope > self.threshold_rms, duck_factor, 1.0)

        # Smooth (Attack/Release)
        smooth_window = int(music_sr * max(self.attack_ms, self.release_ms) / 1000.0)
        gain = uniform_filter1d(gain, size=max(1, smooth_window))

        # Anwenden
        ducked_music = music_data * gain
        mixed = ducked_music + voice_data

        # Clipping vermeiden
        peak = np.abs(mixed).max()
        if peak > 0.95:
            mixed = mixed * (0.95 / peak)

        # Finale Bounds-Pruefung gegen Int16-Overflow
        mixed = np.clip(mixed, -1.0, 1.0)

        # Speichern
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        wavfile.write(str(out), music_sr, (mixed * 32767).astype(np.int16))

        if progress_cb:
            progress_cb(100, "Ducking abgeschlossen")

        return str(out.resolve())


class FrequencyAnalyzer:
    """Rekordbox-Style Frequenzband-Analyse: Zerlegt Audio in Low/Mid/High Bänder.

    Frequenzbereiche (wie Rekordbox/CDJ):
        Low  (Bass/Kicks):   20 - 250 Hz   → Blau
        Mid  (Vocals/Snare): 250 - 4000 Hz → Rosa/Rot
        High (HiHats/Air):   4000 - 20000 Hz → Weiß/Gelb
    """

    # Grenzfrequenzen in Hz
    LOW_MAX = 250
    MID_MAX = 4000
    SR = 22050
    HOP_LENGTH = 512      # ~23ms pro Frame → hochauflösend
    N_FFT = 2048          # Frequenzauflösung: ~10.7 Hz pro Bin

    def analyze(self, file_path: str, progress_cb=None) -> dict:
        """Berechnet Frequenzband-Amplituden + präzises Beatgrid.

        Returns dict mit:
            band_low:  list[float]   Normalisierte Bass-Amplituden [0..1]
            band_mid:  list[float]   Normalisierte Mitten-Amplituden [0..1]
            band_high: list[float]   Normalisierte Höhen-Amplituden [0..1]
            num_samples: int         Anzahl der Zeitschritte
            duration: float          Track-Dauer in Sekunden
            bpm: float               Erkannte BPM
            beat_positions: list[float]  Beat-Zeitstempel in Sekunden
        """
        if progress_cb:
            progress_cb(0, "Lade Audio...")

        y, sr = librosa.load(file_path, sr=self.SR, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        if progress_cb:
            progress_cb(20, "STFT Frequenzanalyse...")

        # Short-Time Fourier Transform → Magnitude-Spektrogramm
        S = np.abs(librosa.stft(y, n_fft=self.N_FFT, hop_length=self.HOP_LENGTH))

        # Frequenz-Bins zu Hz mappen
        freqs = librosa.fft_frequencies(sr=sr, n_fft=self.N_FFT)

        # Frequenzband-Masken
        low_mask = freqs <= self.LOW_MAX
        mid_mask = (freqs > self.LOW_MAX) & (freqs <= self.MID_MAX)
        high_mask = freqs > self.MID_MAX

        # Mittlere Energie pro Band über alle Frequenz-Bins im Band
        band_low = np.mean(S[low_mask, :], axis=0)
        band_mid = np.mean(S[mid_mask, :], axis=0)
        band_high = np.mean(S[high_mask, :], axis=0)

        # Normalisierung: Jedes Band auf [0..1] skalieren (Peak = 1.0)
        def _normalize(arr):
            peak = arr.max()
            if peak > 0:
                return arr / peak
            return arr

        band_low = _normalize(band_low)
        band_mid = _normalize(band_mid)
        band_high = _normalize(band_high)

        if progress_cb:
            progress_cb(50, "Beatgrid-Erkennung...")

        # Präzises Beatgrid via librosa
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=self.HOP_LENGTH)
        if isinstance(tempo, np.ndarray):
            bpm = float(tempo.flat[0])
        else:
            bpm = float(tempo)
        bpm = round(bpm, 1)

        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=self.HOP_LENGTH)
        beat_positions = [round(float(t), 4) for t in beat_times]

        if progress_cb:
            progress_cb(80, "Daten komprimieren...")

        # Downsampling für Speichereffizienz: max ~2000 Samples für DB
        num_samples = len(band_low)
        max_db_samples = 4000
        if num_samples > max_db_samples:
            factor = num_samples / max_db_samples
            indices = np.round(np.arange(0, num_samples, factor)).astype(int)
            indices = indices[indices < num_samples]
            band_low_store = band_low[indices]
            band_mid_store = band_mid[indices]
            band_high_store = band_high[indices]
            store_samples = len(indices)
        else:
            band_low_store = band_low
            band_mid_store = band_mid
            band_high_store = band_high
            store_samples = num_samples

        # Auf 4 Dezimalstellen runden für kompakte JSON-Speicherung
        result = {
            "band_low": [round(float(v), 4) for v in band_low_store],
            "band_mid": [round(float(v), 4) for v in band_mid_store],
            "band_high": [round(float(v), 4) for v in band_high_store],
            "num_samples": store_samples,
            "duration": round(duration, 3),
            "bpm": bpm,
            "beat_positions": beat_positions,
        }

        if progress_cb:
            progress_cb(100, "Frequenzanalyse abgeschlossen")

        return result

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und speichert Waveform + Beatgrid in der DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        result = self.analyze(file_path, progress_cb=progress_cb)

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nach Frequenzanalyse nicht mehr gefunden")

            # BPM + Duration updaten
            # P2-04: BPM immer ueberschreiben (aktuelle Analyse ist praeziser)
            track.bpm = result["bpm"]
            track.duration = result["duration"]

            # DB-07 Fix: Expliziter Query-Check gegen Duplikate
            existing_wd = track.waveform_data or session.query(WaveformData).filter_by(
                audio_track_id=track_id
            ).first()

            if existing_wd:
                existing_wd.num_samples = result["num_samples"]
                existing_wd.duration = result["duration"]
                existing_wd.band_low = json.dumps(result["band_low"])
                existing_wd.band_mid = json.dumps(result["band_mid"])
                existing_wd.band_high = json.dumps(result["band_high"])
            else:
                wd = WaveformData(
                    audio_track_id=track_id,
                    num_samples=result["num_samples"],
                    duration=result["duration"],
                    band_low=json.dumps(result["band_low"]),
                    band_mid=json.dumps(result["band_mid"]),
                    band_high=json.dumps(result["band_high"]),
                )
                session.add(wd)

            session.commit()

            try:
                from services.pacing_service import invalidate_pacing_caches
                invalidate_pacing_caches()
            except Exception as e:
                logger.warning("invalidate_pacing_caches() fehlgeschlagen: %s", e)

        return result
