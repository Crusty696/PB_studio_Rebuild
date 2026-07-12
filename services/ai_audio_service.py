"""AI Audio Service: Demucs Stem Separation + Auto-Ducking + Rekordbox Frequency Analysis."""

import gc
import logging
import os
import subprocess
import tempfile
import time
from functools import wraps
from pathlib import Path

from services.errors import CUDAOutOfMemoryError
from services.ffmpeg_utils import subprocess_kwargs
from services.timeout_constants import FFMPEG_RENDER_TIMEOUT_SEC
from services.startup_checks import get_ffmpeg_bin

import numpy as np
import librosa
import soundfile as sf
from scipy.io import wavfile

# torch/torchaudio werden lazy importiert (nur in StemSeparator benötigt)
# damit das Modul auch ohne CUDA-Installation importierbar ist
try:
    import torch as _torch_module
    import torchaudio as _torchaudio_module
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
from database import AudioTrack, WaveformData, nullpool_session

from services.ffmpeg_utils import sanitize_ffmpeg_error as _sanitize_ffmpeg_error
from services.model_manager import oom_recovery

logger = logging.getLogger(__name__)


def _gpu_execution_locked(func):
    """Serialisiert direkte Demucs-Service-Aufrufe gegen andere GPU-Jobs."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        from services.model_manager import GPU_EXECUTION_LOCK
        with GPU_EXECUTION_LOCK:
            return func(*args, **kwargs)
    return wrapper

def _get_stems_dir() -> Path:
    """Return stems directory for the current project (lazy APP_ROOT read).

    BUG-FIX: Was module-level constant that became stale after set_project().
    Now reads APP_ROOT at call time so project switches are respected.
    """
    import database.session as _session
    return _session.APP_ROOT / "storage" / "stems"


# B-510: Chunk-Groesse fuer das Einlesen des Demucs-Inputs (Sekunden).
STEM_LOAD_CHUNK_SECONDS = 30
# B-510: Kontext-Rand pro Chunk fuer chunk-weises Resampling (Sekunden).
# Muss nur die Sinc-Filterbreite von torchaudio.functional.resample abdecken
# (Default lowpass_filter_width=6 -> wenige ms); 1 s ist sehr konservativ.
STEM_RESAMPLE_MARGIN_SECONDS = 1.0


def _finalize_stem_waveform(waveform, sr: int, target_sr: int, torchaudio_module):
    """Legacy-Fallback (B-510): Full-Array-Resample + Kanal-Anpassung auf (2, n).

    Identisches Verhalten wie der alte Code in separate() vor B-510:
    Resample auf target_sr, Mono->Stereo via repeat, >2 Kanaele -> erste 2.
    Wird nur noch benutzt, wenn der chunked soundfile-Pfad nicht greift
    (Formate, die torchaudio kann, libsndfile aber nicht).
    """
    if sr != target_sr:
        waveform = torchaudio_module.functional.resample(waveform, sr, target_sr)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    return waveform


def _chunked_soundfile_load(src: Path, target_sr: int, torchaudio_module, should_stop=None):
    """B-510: Chunk-weises Laden via soundfile in vorallokiertes (2, n)-float32-Array.

    Vermeidet die transienten Vollkopien des alten Pfads (torchaudio-Full-Load
    @ nativer SR + Full-Resample-Zweitkopie + Mono->Stereo-Repeat ≈ bis zu 3x
    Mix-Groesse Peak-RAM; 3h-Mix ~7 GB transient). Peak ist jetzt das finale
    Ziel-Array + ein ~32-s-Chunk-Puffer.

    Resampling erfolgt pro Chunk mit Kontext-Rand; Chunk-Starts liegen auf dem
    Polyphasen-Raster (Vielfache von file_sr // gcd(file_sr, target_sr)),
    dadurch identische Filterphasen wie beim Full-Signal-Resample. Numerische
    Aequivalenz: tests/test_services/test_stem_separator_audio_decode.py
    (test_chunked_loader_matches_legacy_full_load).
    """
    import math
    if not _TORCH_AVAILABLE:
        raise RuntimeError("torch nicht verfuegbar fuer chunked Stem-Input-Load")
    torch = _torch_module
    with sf.SoundFile(str(src), mode="r") as f:
        file_sr = int(f.samplerate)
        total_in = int(f.frames)
        if file_sr <= 0 or total_in <= 0:
            raise RuntimeError(f"Audio-Datei leer oder Laenge unbekannt: {src}")
        if file_sr == target_sr:
            total_out = total_in
            margin = 0
        else:
            total_out = -((-total_in * target_sr) // file_sr)  # ceil-div, exakt wie torchaudio
            poly = file_sr // math.gcd(file_sr, target_sr)
            margin = int(math.ceil(STEM_RESAMPLE_MARGIN_SECONDS * file_sr / poly)) * poly
        out = torch.zeros((2, total_out), dtype=torch.float32)
        # chunk_in ist Vielfaches von poly (poly teilt file_sr) -> Raster-aligned
        chunk_in = int(STEM_LOAD_CHUNK_SECONDS) * file_sr
        pos_in = 0
        pos_out = 0
        while pos_in < total_in:
            # B-524: Abbruch-Check pro Lade-Chunk. Ohne ihn lief der CPU-Loader
            # eines langen Mixes nach User-Cancel minutenlang weiter (Status
            # haengt auf "0% - Initialisierung") und hielt den GPU_EXECUTION_LOCK
            # → wartende Proxy-/GPU-Folge-Tasks blockiert.
            if should_stop and should_stop():
                raise RuntimeError("Stem-Separation abgebrochen (User-Cancel)")
            core_len = min(chunk_in, total_in - pos_in)
            lead = min(pos_in, margin)
            read_start = pos_in - lead
            read_stop = min(total_in, pos_in + core_len + margin)
            f.seek(read_start)
            block = f.read(frames=read_stop - read_start, dtype="float32", always_2d=True)
            data = torch.from_numpy(np.ascontiguousarray(block.T))
            del block
            if data.shape[0] > 2:
                data = data[:2].contiguous()
            if file_sr != target_sr:
                data = torchaudio_module.functional.resample(data, file_sr, target_sr)
                out_lead = (lead * target_sr) // file_sr  # lead raster-aligned -> exakt
                out_core = min(total_out - pos_out, -((-core_len * target_sr) // file_sr))
                seg = data[:, out_lead:out_lead + out_core]
            else:
                seg = data[:, lead:lead + core_len]
            # Mono (1, n) broadcastet beim Zuweisen auf beide Kanaele
            out[:, pos_out:pos_out + seg.shape[1]] = seg
            pos_out += seg.shape[1]
            pos_in += core_len
            del data, seg
        if pos_out != total_out:
            raise RuntimeError(
                f"Chunked-Load Laengen-Mismatch: {pos_out} != {total_out} ({src})"
            )
    return out


def _load_audio_for_stem_separation(
    src: Path,
    torchaudio_module,
    target_sr: int,
    should_stop=None,
):
    """Load audio for Demucs as (2, n) float32 waveform at ``target_sr``.

    B-510: Primaerpfad ist chunk-weises soundfile-Lesen in ein vorallokiertes
    Ziel-Array (finale SR, 2 Kanaele). Fallback 1: torchaudio-Full-Load
    (Formate, die libsndfile nicht kann). Fallback 2: FFmpeg-Decode in
    temp-WAV (bereits 2ch float32 @ target_sr), erneut chunk-weise gelesen.

    Returns:
        (waveform, sr) mit waveform-Shape (2, n) und sr == target_sr.
    """
    try:
        return _chunked_soundfile_load(src, target_sr, torchaudio_module, should_stop), target_sr
    except Exception as sf_error:
        # B-524: User-Cancel NICHT als Lade-Fehler behandeln (sonst liefe der
        # torchaudio-/FFmpeg-Fallback trotz Abbruch weiter).
        if should_stop and should_stop():
            raise
        logger.debug(
            "[StemSeparator] Chunked soundfile-Load fehlgeschlagen (%s) — torchaudio-Fallback.",
            sf_error,
        )
    try:
        waveform, sr = torchaudio_module.load(str(src))
        return _finalize_stem_waveform(waveform, sr, target_sr, torchaudio_module), target_sr
    except Exception as first_error:
        ffmpeg_bin = str(get_ffmpeg_bin())
        tmp_wav = tempfile.NamedTemporaryFile(prefix="pb_stem_decode_", suffix=".wav", delete=False)
        tmp_wav_path = Path(tmp_wav.name)
        tmp_wav.close()
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-f",
            "wav",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "2",
            "-ar",
            str(target_sr),
            str(tmp_wav_path),
        ]
        kwargs = subprocess_kwargs()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=FFMPEG_RENDER_TIMEOUT_SEC,
                check=False,
                **kwargs,
            )
        except Exception as ffmpeg_error:
            tmp_wav_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Audio-Datei konnte weder via torchaudio noch FFmpeg geladen werden: {first_error}"
            ) from ffmpeg_error

        if result.returncode != 0 or not tmp_wav_path.exists() or tmp_wav_path.stat().st_size == 0:
            tmp_wav_path.unlink(missing_ok=True)
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                "Audio-Datei konnte weder via torchaudio noch FFmpeg geladen werden: "
                f"{first_error}; FFmpeg: {_sanitize_ffmpeg_error(stderr_text)}"
            ) from first_error

        try:
            # B-510: temp-WAV ist bereits 2ch float32 @ target_sr -> chunk-weises
            # Lesen ohne Resample; torchaudio-Full-Load nur als letzter Fallback.
            try:
                waveform = _chunked_soundfile_load(tmp_wav_path, target_sr, torchaudio_module)
            except Exception:
                wf, sr = torchaudio_module.load(str(tmp_wav_path))
                waveform = _finalize_stem_waveform(wf, sr, target_sr, torchaudio_module)
        except Exception as wav_error:
            raise RuntimeError(
                "Audio-Datei wurde via FFmpeg dekodiert, aber temp WAV konnte nicht geladen werden: "
                f"{wav_error}"
            ) from wav_error
        finally:
            tmp_wav_path.unlink(missing_ok=True)

        logger.info(
            "[StemSeparator] Audio via FFmpeg geladen: %s, SR=%s, Samples=%s",
            src.name,
            target_sr,
            waveform.shape[1],
        )
        return waveform, target_sr

# Chunk-Dauer in Sekunden fuer VRAM-schonendes Processing
CHUNK_SECONDS = 30
# Overlap in Sekunden um Artefakte an Chunk-Grenzen zu vermeiden
OVERLAP_SECONDS = 2
STEM_MAX_CHUNKS_ENV = "PB_STEM_MAX_CHUNKS"


def _read_positive_int_env(name: str) -> int | None:
    value = os.environ.get(name)
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("[StemSeparator] Ignoriere ungueltiges %s=%r", name, value)
        return None
    if parsed <= 0:
        logger.warning("[StemSeparator] Ignoriere nicht-positives %s=%r", name, value)
        return None
    return parsed


def _raise_if_stem_diagnostic_chunk_limit_reached(chunk_index: int, num_chunks: int) -> None:
    max_chunks = _read_positive_int_env(STEM_MAX_CHUNKS_ENV)
    if max_chunks is None or max_chunks >= num_chunks:
        return
    if chunk_index >= max_chunks:
        raise RuntimeError(
            "Stem-Separation Diagnose-Limit erreicht: "
            f"{max_chunks}/{num_chunks} Chunks verarbeitet; keine Teil-Stems gespeichert. "
            f"{STEM_MAX_CHUNKS_ENV} entfernen fuer Voll-Lauf."
        )


def _cuda_free_gb(get_cuda_memory_info_bytes) -> float | None:
    try:
        free_bytes, _total_bytes = get_cuda_memory_info_bytes(0)
    except Exception as exc:
        logger.warning("[StemSeparator] CUDA-Memory-Diagnose fehlgeschlagen: %s", exc)
        return None
    if free_bytes <= 0:
        return None
    return free_bytes / (1024**3)


class _StreamingStemWriter:
    """Write overlapped Demucs chunks without holding full mix-length stems in RAM."""

    def __init__(
        self,
        stem_dir: Path,
        source_names: list[str],
        channels: int,
        sample_rate: int,
    ) -> None:
        self._files = {}
        self.paths = {}
        self._pending = None
        self._pending_weight = None
        stem_dir.mkdir(parents=True, exist_ok=True)
        for stem_name in source_names:
            stem_path = stem_dir / f"{stem_name}.wav"
            self.paths[stem_name] = str(stem_path.resolve())
            self._files[stem_name] = sf.SoundFile(
                str(stem_path),
                mode="w",
                samplerate=sample_rate,
                channels=channels,
                subtype="FLOAT",
            )

    def write_chunk(
        self,
        weighted_estimates,
        fade,
        source_names: list[str],
        overlap_samples: int,
        is_last: bool,
    ) -> None:
        chunk_len = int(weighted_estimates.shape[-1])
        cursor = 0

        if self._pending is not None:
            overlap_len = min(
                int(self._pending.shape[-1]),
                chunk_len,
                max(0, int(overlap_samples)),
            )
            if overlap_len > 0:
                weight = self._clamped_weight(
                    self._pending_weight[:overlap_len] + fade[:overlap_len]
                )
                merged = (
                    self._pending[:, :, :overlap_len] + weighted_estimates[:, :, :overlap_len]
                ) / weight.unsqueeze(0).unsqueeze(0)
                self._write_samples(merged, source_names)
                cursor = overlap_len
            self._pending = None
            self._pending_weight = None

        keep_tail = 0 if is_last else min(max(0, int(overlap_samples)), max(0, chunk_len - cursor))
        write_end = chunk_len - keep_tail
        if write_end > cursor:
            weight = self._clamped_weight(fade[cursor:write_end])
            normalized = weighted_estimates[:, :, cursor:write_end] / weight.unsqueeze(0).unsqueeze(0)
            self._write_samples(normalized, source_names)

        if keep_tail:
            self._pending = weighted_estimates[:, :, write_end:].clone()
            self._pending_weight = fade[write_end:].clone()

    def close(self, source_names: list[str]) -> None:
        try:
            if self._pending is not None:
                weight = self._clamped_weight(self._pending_weight)
                normalized = self._pending / weight.unsqueeze(0).unsqueeze(0)
                self._write_samples(normalized, source_names)
        finally:
            self._pending = None
            self._pending_weight = None
            for file_obj in self._files.values():
                file_obj.close()

    def abort(self) -> None:
        self._pending = None
        self._pending_weight = None
        for file_obj in self._files.values():
            file_obj.close()
        for path in self.paths.values():
            Path(path).unlink(missing_ok=True)

    def _write_samples(self, samples, source_names: list[str]) -> None:
        for idx, stem_name in enumerate(source_names):
            data = samples[idx].detach().cpu().numpy().T
            self._files[stem_name].write(data)

    @staticmethod
    def _clamped_weight(weight):
        if (
            _TORCH_AVAILABLE
            and getattr(weight, "device", None) is not None
            and weight.device.type == "cpu"
            and weight.dtype == _torch_module.float16
        ):
            weight = weight.float()
        return weight.clamp(min=1e-8)


class StemSeparator:
    """Trennt Audio via Demucs Python API in Vocals, Drums, Bass, Other.

    Verwendet Chunking (30s Bloecke) und erzwingt CUDA um VRAM-Limits
    (z.B. GTX 1060 6GB) einzuhalten und CPU-Fallback zu vermeiden.
    """

    @staticmethod
    def _apply_demucs_model_locked(apply_model_fn, model_obj, chunk, **kwargs):
        from services.model_manager import GPU_EXECUTION_LOCK
        with GPU_EXECUTION_LOCK:
            return apply_model_fn(model_obj, chunk, **kwargs)

    @oom_recovery
    @_gpu_execution_locked
    def separate(self, file_path: str, model: str = "htdemucs",
                 progress_cb=None, should_stop=None,
                 output_dir: str | Path | None = None) -> dict[str, str]:
        """Fuehrt Demucs Stem Separation mit Chunking + CUDA-Zwang aus.

        ``output_dir`` erlaubt Pipeline-Aufrufern, direkt in ihr kurzes,
        track-id-zentriertes Ziel zu schreiben. Ohne Override bleibt das
        Legacy-Layout ``storage/stems/<model>/<source-stem>`` erhalten.

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

        _get_stems_dir().mkdir(parents=True, exist_ok=True)
        src = Path(file_path)

        # ── 1. VRAM freigeben: alle anderen Modelle entladen ──
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.warning("ModelManager.unload() vor Demucs fehlgeschlagen: %s", e)
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # ── 2. Device bestimmen (GPU bevorzugt, CPU-Fallback erlaubt) ──
        if torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info(f"[StemSeparator] GPU erkannt: {torch.cuda.get_device_name(0)} "
                  f"({torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB VRAM)")
        else:
            device = torch.device("cpu")
            logger.warning(
                "[StemSeparator] Keine CUDA-GPU erkannt — CPU-Fallback aktiv. "
                "Stem-Separation laeuft deutlich langsamer (5-10x). "
                "Fuer GPU-Beschleunigung: NVIDIA-Treiber + torch CUDA installieren."
            )

        if progress_cb:
            progress_cb(5, "Lade Demucs-Modell...")

        # ── 3. Demucs-Modell laden (Python API) ──
        try:
            from demucs.pretrained import get_model
            from demucs.apply import apply_model
        except ImportError as e:
            from services.errors import MLUnavailableError
            raise MLUnavailableError(
                feature="Stem-Separation",
                reason="demucs nicht installiert. Bitte installieren: pip install demucs",
            ) from e
        from services.model_manager import GPU_LOAD_LOCK, get_cuda_memory_info_bytes
        with GPU_LOAD_LOCK:
            try:
                demucs_model = get_model(model)
            except (OSError, EnvironmentError) as e:
                from services.errors import MLModelNotFoundError
                raise MLModelNotFoundError(
                    model,
                    hint=(
                        "Demucs laedt Modelle automatisch beim ersten Start. "
                        "Stelle sicher dass eine Internetverbindung besteht."
                    ),
                ) from e
            try:
                demucs_model.to(device)
            except RuntimeError:
                # B-112 / BUG-A7: guard empty_cache so a CPU-only torch
                # build does not raise AssertionError and mask the
                # original RuntimeError.
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
                raise CUDAOutOfMemoryError(operation=f"Demucs '{model}' laden")
            demucs_model.eval()
        logger.info(f"[StemSeparator] Modell '{model}' geladen auf {device}")

        # B-524: Abbruch-Check vor dem (potentiell minutenlangen) Audio-Load,
        # damit ein Cancel zwischen Modell- und Audio-Load sofort den
        # GPU_EXECUTION_LOCK freigibt statt erst nach dem Laden.
        if should_stop and should_stop():
            raise RuntimeError("Stem-Separation abgebrochen (User-Cancel)")

        if progress_cb:
            progress_cb(10, "Lade Audio-Datei...")

        # ── 4. Audio laden ──
        # Demucs erwartet die Samplerate des Modells (typisch 44100 Hz).
        # Stems werden in model_sr gespeichert. Die Pacing-Pipeline (pacing_service.py)
        # laedt Stems spaeter mit librosa (Default 22050 Hz) — das Downsampling ist beabsichtigt.
        model_sr = demucs_model.samplerate
        # B-510: Loader liefert bereits (2, n) float32 @ model_sr (chunk-weises
        # Lesen + Resample pro Chunk in vorallokiertes Ziel-Array). Die frueheren
        # Full-Array-Kopien (Resample-Zweitkopie + Mono->Stereo-Repeat) entfallen.
        waveform, sr = _load_audio_for_stem_separation(src, torchaudio, model_sr, should_stop=should_stop)

        # B-524: Abbruch-Check direkt nach dem Audio-Load, bevor das
        # Chunk-Setup/erste apply_model laeuft.
        if should_stop and should_stop():
            raise RuntimeError("Stem-Separation abgebrochen (User-Cancel)")

        total_samples = waveform.shape[1]
        # D-01 Fix: chunk_seconds als lokale Variable, damit VRAM-Check sie reduzieren kann
        chunk_seconds = CHUNK_SECONDS
        overlap_seconds = OVERLAP_SECONDS

        # ── 5. Chunk-weise verarbeiten ──
        # Demucs Source-Namen ermitteln
        source_names = demucs_model.sources  # z.B. ['drums', 'bass', 'other', 'vocals']
        num_sources = len(source_names)

        # D-01 Fix: VRAM-Budget pruefen — bei wenig VRAM Chunk-Groesse halbieren
        if torch.cuda.is_available():
            vram_free, _vram_total = get_cuda_memory_info_bytes(0)
            vram_free_gb = vram_free / (1024**3)
            if vram_free_gb < 2.0:
                chunk_seconds = max(10, chunk_seconds // 2)
                logger.warning(
                    "[StemSeparator] Nur %.1f GB VRAM frei — Chunk-Groesse reduziert auf %ds",
                    vram_free_gb, chunk_seconds,
                )

        chunk_samples = chunk_seconds * sr
        overlap_samples = overlap_seconds * sr
        step_samples = chunk_samples - overlap_samples

        # Berechne Chunk-Anzahl
        if total_samples <= chunk_samples:
            num_chunks = 1
        else:
            num_chunks = 1 + int(np.ceil((total_samples - chunk_samples) / step_samples))

        logger.info(f"[StemSeparator] Audio: {total_samples / sr:.1f}s, "
              f"SR={sr}, Chunks={num_chunks} (je {chunk_seconds}s, {overlap_seconds}s Overlap)")

        if progress_cb:
            progress_cb(15, f"Starte Stem-Trennung in {num_chunks} Chunks...")

        # A-02 Fix: RAM-Budget pruefen — result_stems + weight_sum koennen bei
        # langen Mixes >5GB RAM belegen. Immer float32 fuer Qualitaet,
        # aber Warnung bei hohem geschaetztem RAM-Verbrauch.
        estimated_ram_gb = (num_sources * waveform.shape[0] * total_samples * 4) / (1024**3)
        stream_stems = estimated_ram_gb > 3.0
        stem_dir = (
            Path(output_dir)
            if output_dir is not None
            else _get_stems_dir() / model / src.stem
        )
        streaming_writer = None
        streaming_paths = None
        if estimated_ram_gb > 8.0:
            logger.warning(
                "[StemSeparator] Grosser Output — %.1f GB RAM fuer Akkumulator vermieden; "
                "schreibe %.0f min Audio streaming auf Disk.",
                estimated_ram_gb, total_samples / sr / 60,
            )
            if progress_cb:
                progress_cb(15, f"Streaming-Output aktiv (~{estimated_ram_gb:.0f} GB RAM vermieden)")
        elif estimated_ram_gb > 3.0:
            # B-LOG: nur ein %-Format -> nur ein Argument (frueher 2 Args -> TypeError im Logger).
            logger.info(
                "[StemSeparator] Output: %.1f GB RAM fuer Akkumulator vermieden; Streaming aktiv.",
                estimated_ram_gb,
            )

        if stream_stems:
            streaming_writer = _StreamingStemWriter(
                stem_dir,
                list(source_names),
                int(waveform.shape[0]),
                int(sr),
            )
            result_stems = None
            weight_sum = None
        else:
            # Ergebnis-Tensor fuer kurze Audio-Dateien (Crossfade-Akkumulator) — immer float32
            result_stems = torch.zeros(num_sources, waveform.shape[0], total_samples, dtype=torch.float32)
            weight_sum = torch.zeros(1, total_samples, dtype=torch.float32)

        # B-601 Fix: GPU-Code in try/finally um ANY Exception zu handhaben
        try:
            for i in range(num_chunks):
                # F-008 Fix: Abbruch-Check
                if should_stop and should_stop():
                    logger.info("[StemSeparator] Abbruch durch Benutzer.")
                    raise RuntimeError("Stem-Separation abgebrochen (User-Cancel)")
                _raise_if_stem_diagnostic_chunk_limit_reached(i, num_chunks)

                start = i * step_samples
                end = min(start + chunk_samples, total_samples)
                chunk = waveform[:, start:end]
                chunk_started = time.perf_counter()

                logger.info(f"[StemSeparator] Verarbeite Chunk {i + 1}/{num_chunks} "
                      f"auf {device.type.upper()} "
                      f"({start / sr:.1f}s - {end / sr:.1f}s)...")

                # Chunk auf GPU, Batch-Dimension hinzufuegen: (1, channels, samples)
                chunk_gpu = chunk.unsqueeze(0).to(device)

                # D-04 Fix: try/except um apply_model() — bei OOM Chunk halbieren und einmal retrien
                with torch.no_grad():
                    try:
                        vram_before_gb = _cuda_free_gb(get_cuda_memory_info_bytes) if torch.cuda.is_available() else None
                        apply_started = time.perf_counter()
                        # apply_model gibt (1, sources, channels, samples) zurueck
                        # DOPPELTER OVERLAP: internes Demucs-Overlap (25% der Chunk-Laenge)
                        # PLUS externes 2s Crossfade-Overlap zwischen Chunks (OVERLAP_SECONDS).
                        # Erhoehte Qualitaet an Chunk-Grenzen, aber ~30% langsamer.
                        estimates = self._apply_demucs_model_locked(
                            apply_model,
                            demucs_model, chunk_gpu,
                            overlap=0.25,
                            progress=False,
                        )
                        apply_elapsed = time.perf_counter() - apply_started
                        vram_after_gb = _cuda_free_gb(get_cuda_memory_info_bytes) if torch.cuda.is_available() else None
                        logger.info(
                            "[StemSeparator] Chunk %d/%d apply_model fertig: %.2fs, VRAM frei vor/nach: %s/%s GB",
                            i + 1,
                            num_chunks,
                            apply_elapsed,
                            f"{vram_before_gb:.2f}" if vram_before_gb is not None else "n/a",
                            f"{vram_after_gb:.2f}" if vram_after_gb is not None else "n/a",
                        )
                    except RuntimeError as _oom_exc:
                        # B-356 Fix: Nur echte CUDA-OOM-Fehler triggern die
                        # Chunk-Halbierung. Shape-/Model-/I/O-RuntimeErrors
                        # werden unveraendert weitergereicht statt als VRAM-
                        # Fehler maskiert zu werden.
                        _cuda_oom = (
                            hasattr(torch.cuda, "OutOfMemoryError")
                            and isinstance(_oom_exc, torch.cuda.OutOfMemoryError)
                        ) or "out of memory" in str(_oom_exc).lower()
                        if not _cuda_oom:
                            raise
                        logger.warning(
                            "[StemSeparator] OOM bei Chunk %d/%d — halbiere Chunk und retrie...",
                            i + 1, num_chunks,
                        )
                        del chunk_gpu
                        torch.cuda.empty_cache()
                        gc.collect()
                        # M-15 Fix: Retry mit halber Chunk-Laenge (nur den aktuellen Chunk)
                        # Allocate and process chunks sequentially to avoid double GPU allocation
                        half = chunk.shape[1] // 2
                        chunk_gpu_a = chunk[:, :half].unsqueeze(0).to(device)
                        try:
                            est_a = self._apply_demucs_model_locked(
                                apply_model,
                                demucs_model,
                                chunk_gpu_a,
                                overlap=0.25,
                                progress=False,
                            )
                            del chunk_gpu_a
                            torch.cuda.empty_cache()
                            # Only allocate second chunk after first is freed
                            chunk_gpu_b = chunk[:, half:].unsqueeze(0).to(device)
                            est_b = self._apply_demucs_model_locked(
                                apply_model,
                                demucs_model,
                                chunk_gpu_b,
                                overlap=0.25,
                                progress=False,
                            )
                            del chunk_gpu_b
                            torch.cuda.empty_cache()
                            estimates = torch.cat([est_a, est_b], dim=-1)
                            del est_a, est_b
                        except RuntimeError as _retry_exc:
                            torch.cuda.empty_cache()
                            gc.collect()
                            # B-356 Fix: Auch im Retry-Pfad nur echte CUDA-OOM
                            # als CUDAOutOfMemoryError melden; andere
                            # RuntimeErrors original durchreichen.
                            _retry_oom = (
                                hasattr(torch.cuda, "OutOfMemoryError")
                                and isinstance(_retry_exc, torch.cuda.OutOfMemoryError)
                            ) or "out of memory" in str(_retry_exc).lower()
                            if not _retry_oom:
                                raise
                            raise CUDAOutOfMemoryError(
                                operation=f"apply_model Chunk {i + 1}/{num_chunks} (nach Retry)"
                            )

                # Zurueck auf CPU — squeeze(0) entfernt Batch-Dim (immer 1 bei Einzelverarbeitung)
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

                # Gewichtete Addition
                weighted_estimates = estimates_cpu[:, :, :chunk_len] * fade.unsqueeze(0).unsqueeze(0)
                write_started = time.perf_counter()
                if streaming_writer is not None:
                    streaming_writer.write_chunk(
                        weighted_estimates,
                        fade,
                        list(source_names),
                        overlap_samples,
                        i == num_chunks - 1,
                    )
                else:
                    for s in range(num_sources):
                        result_stems[s, :, start:end] += weighted_estimates[s]
                    weight_sum[0, start:end] += fade
                logger.info(
                    "[StemSeparator] Chunk %d/%d CPU/Write fertig: %.2fs, Gesamt-Chunk: %.2fs",
                    i + 1,
                    num_chunks,
                    time.perf_counter() - write_started,
                    time.perf_counter() - chunk_started,
                )

                # ── VRAM sofort freigeben ──
                # Sicheres Loeschen: chunk_gpu kann bei OOM-Retry bereits geloescht sein
                chunk_gpu = None
                estimates = None
                estimates_cpu = None
                weighted_estimates = None
                gc.collect()
                torch.cuda.empty_cache()

                # Progress: 15% bis 85% fuer Chunk-Processing
                if progress_cb:
                    pct = 15 + int(70 * (i + 1) / num_chunks)
                    progress_cb(pct, f"Chunk {i + 1}/{num_chunks} fertig")

            # Normalisierung durch Gewichtssumme (Crossfade — AUSSERHALB der for-Schleife)
            if streaming_writer is not None:
                streaming_writer.close(list(source_names))
                streaming_paths = dict(streaming_writer.paths)
                streaming_writer = None
            else:
                weight_sum = weight_sum.clamp(min=1e-8)
                for s in range(num_sources):
                    result_stems[s] /= weight_sum
        finally:
            if streaming_writer is not None:
                try:
                    streaming_writer.abort()
                except Exception as cleanup_error:
                    logger.warning("[StemSeparator] Streaming-Cleanup fehlgeschlagen: %s", cleanup_error)
            # B-601 Fix: Cleanup falls Exception in Chunk-Processing
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # ── 6. Modell entladen ──
        del demucs_model
        gc.collect()
        torch.cuda.empty_cache()
        logger.info("[StemSeparator] Modell entladen, VRAM freigegeben")

        if progress_cb:
            progress_cb(90, "Speichere Stems als WAV...")

        # ── 7. Stems als WAV speichern ──
        if streaming_paths is not None:
            stems = dict(streaming_paths)
            for stem_name, stem_path in stems.items():
                logger.info(f"[StemSeparator] Gespeichert: {stem_name} -> {stem_path}")
        else:
            stem_dir.mkdir(parents=True, exist_ok=True)
            stems = {}
            for idx, stem_name in enumerate(source_names):
                stem_path = stem_dir / f"{stem_name}.wav"
                torchaudio.save(str(stem_path), result_stems[idx], sr)
                stems[stem_name] = str(stem_path.resolve())
                logger.info(f"[StemSeparator] Gespeichert: {stem_name} -> {stem_path}")

        # CPU-RAM freigeben: result_stems + weight_sum können >5GB sein bei langen Mixes
        if result_stems is not None:
            del result_stems
        if weight_sum is not None:
            del weight_sum
        gc.collect()

        if progress_cb:
            progress_cb(100, "Stem Separation abgeschlossen")

        return stems

    def separate_to(self, file_path: str, out_dir: str, subtype: str = "PCM_24",
                    model: str = "htdemucs", progress_cb=None, should_stop=None) -> dict[str, str]:
        """Plan AUDIO-ANALYSIS-V2 T2.1 (A-2 + Q-C): separiert Stems direkt nach
        ``out_dir/{name}.wav`` als ``subtype`` (default PCM_24).

        Wrappt ``separate()`` und re-encoded/kopiert die WAVs ins track-id-zentrierte
        Layout (``storage/stems/<track_id>/``) statt ins Alt-Layout. Atomic-write
        pflichtig (T2.4): tmp+os.replace pro WAV (Windows-safe).

        OTK-018 Bucket-B: additiv aus sandbox/audio-analysis-v2@2cd9ca1 portiert,
        damit StemGenStage den Demucs-First-Stage real fahren kann.
        """
        import shutil
        import torchaudio
        out_dir_path = Path(out_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)

        # 1. Direkt ins kurze track-id-zentrierte Layout schreiben. Dadurch
        # entsteht unter Windows kein dateiname-basierter Langpfad mehr.
        alt_stems = self.separate(
            file_path,
            model=model,
            progress_cb=progress_cb,
            should_stop=should_stop,
            output_dir=out_dir_path,
        )

        # 2. Re-encode/copy nach neuem Layout mit PCM_24 + atomic-write.
        new_stems: dict[str, str] = {}
        tmp_files: list[Path] = []
        try:
            for name, alt_path in alt_stems.items():
                target = out_dir_path / f"{name}.wav"
                # tmp-Datei MUSS auf .wav enden, sonst scheitert die torchaudio-
                # Format-Inferenz ("Unsupported format: tmp"). os.replace ist
                # trotzdem atomic (gleiches Verzeichnis).
                tmp_target = out_dir_path / f"{name}.tmp.wav"
                tmp_files.append(tmp_target)
                if subtype == "PCM_24":
                    waveform, sr = torchaudio.load(str(alt_path))
                    torchaudio.save(str(tmp_target), waveform, sr,
                                    encoding="PCM_S", bits_per_sample=24)
                else:
                    shutil.copyfile(alt_path, tmp_target)
                os.replace(str(tmp_target), str(target))
                new_stems[name] = str(target.resolve())
        except Exception:
            for tmp in tmp_files:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            raise

        return new_stems

    def separate_and_store(self, track_id: int, progress_cb=None, should_stop=None) -> dict:
        """Separiert Stems und speichert Pfade in der DB.

        B-072: Per-Track-Lock via ``audio_service.track_lock`` (B-143-Refcount-
        Pattern). Vorher liefen zwei parallele ``separate_and_store``-Calls
        auf demselben Track ueber den ``GPU_EXECUTION_LOCK`` zwar
        sequentiell, schrieben aber beide auf denselben
        ``vocals.wav``-Pfad → race wer am Ende die DB committet, plus
        wasted Demucs-Run (~60 s GTX 1060). Lock serialisiert *gleichen*
        Track, *unterschiedliche* Tracks bleiben parallel.
        """
        from services.audio_service import track_lock

        with track_lock(track_id):
            with nullpool_session() as session:
                track = session.get(AudioTrack, track_id)
                if track is None:
                    raise ValueError(f"AudioTrack {track_id} nicht gefunden")
                file_path = track.file_path

            try:
                stems = self.separate(
                    file_path,
                    progress_cb=progress_cb,
                    should_stop=should_stop,
                )
            except (OSError, IOError, ValueError, RuntimeError) as e:
                raise RuntimeError(
                    f"Stem-Separation fehlgeschlagen fuer Track {track_id}: {e}"
                ) from e

            # M-14 Fix: Use nullpool_session() to avoid "database is locked"
            # under concurrent writes
            with nullpool_session() as session:
                track = session.get(AudioTrack, track_id)
                if track is None:
                    raise ValueError(
                        f"AudioTrack {track_id} nach Separation nicht mehr gefunden"
                    )
                track.stem_vocals_path = stems.get("vocals")
                track.stem_drums_path = stems.get("drums")
                track.stem_bass_path = stems.get("bass")
                track.stem_other_path = stems.get("other")
                try:
                    session.commit()
                except Exception:  # broad catch intentional — SQLAlchemy commit can raise many error types
                    session.rollback()
                    raise

        return stems


def _run_ffmpeg_cancellable(
    cmd: list[str],
    timeout: int,
    should_stop=None,
) -> tuple[int, str]:
    """B-074: subprocess.run-Aequivalent mit Cancel-Watchdog fuer den
    AutoDucker-Konvertierungspfad.

    Faehrt ``cmd`` via Popen, polled ``should_stop`` alle 200ms,
    terminiert den Prozess bei True. Wenn ``should_stop`` None ist,
    faellt es auf blockierendes ``subprocess.run`` zurueck (alter Pfad).

    Returns: ``(returncode, stderr_decoded)``.
    Raises: ``RuntimeError("Auto-Ducking abgebrochen (User-Cancel)")``
    wenn der Cancel-Pfad gegriffen hat.
    """
    import threading
    import time as _time

    kwargs: dict = subprocess_kwargs()

    if should_stop is None:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout, **kwargs,
        )
        stderr_text = (
            result.stderr.decode("utf-8", errors="replace")
            if isinstance(result.stderr, bytes)
            else (result.stderr or "")
        )
        return result.returncode, stderr_text

    process = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **kwargs,
    )
    cancelled = threading.Event()

    def _watch() -> None:
        while process.poll() is None:
            try:
                if should_stop():
                    cancelled.set()
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
            except Exception as exc:  # broad: watchdog must keep running
                logger.warning(
                    "[AutoDucker-Cancel] should_stop raised: %s — Watchdog endet.", exc,
                )
                return
            _time.sleep(0.2)

    watchdog = threading.Thread(target=_watch, daemon=True)
    watchdog.start()
    try:
        _stdout, stderr_bytes = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        _stdout, stderr_bytes = process.communicate()
    finally:
        watchdog.join(timeout=2.0)

    if cancelled.is_set():
        raise RuntimeError("Auto-Ducking abgebrochen (User-Cancel)")

    stderr_text = (
        stderr_bytes.decode("utf-8", errors="replace")
        if isinstance(stderr_bytes, bytes)
        else (stderr_bytes or "")
    )
    return process.returncode, stderr_text


class AutoDucker:
    """Senkt Musik automatisch ab wenn Sprache erkannt wird."""

    def __init__(self, duck_db: float = -12.0, attack_ms: float = 200.0,
                 release_ms: float = 500.0, threshold_rms: float = 0.02):
        self.duck_db = duck_db
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.threshold_rms = threshold_rms

    def create_ducked_audio(self, music_path: str, voice_path: str,
                            output_path: str, progress_cb=None,
                            should_stop=None) -> str:
        """Erstellt eine geduckte Version: Musik wird leiser wenn Voice aktiv.

        Versucht FFmpeg, faellt auf Scipy zurueck bei Fehler.

        B-074: ``should_stop`` ist optional eine Callable[[], bool]. Wenn
        gesetzt, werden die zwei FFmpeg-Konvertierungs-Subprocesses ueber
        Popen + Watchdog gestartet (terminierbar bis 5s nach Cancel-
        Signal), und die scipy-Ducking-Phase prueft den Flag vor dem Lauf.
        Damit reagiert "Cancel" innerhalb von <5s statt bis zu 300s
        (FFMPEG_RENDER_TIMEOUT_SEC).
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
                if should_stop is not None and should_stop():
                    raise RuntimeError("Auto-Ducking abgebrochen (User-Cancel)")
                # H-11 FIX: Use managed ffmpeg binary instead of bare "ffmpeg"
                cmd = [get_ffmpeg_bin(), "-y", "-i", src, "-ar", "44100", "-ac", "1",
                       "-c:a", "pcm_s16le", str(dst)]
                returncode, stderr_text = _run_ffmpeg_cancellable(
                    cmd,
                    timeout=FFMPEG_RENDER_TIMEOUT_SEC,
                    should_stop=should_stop,
                )
                if returncode != 0:
                    raise RuntimeError(
                        f"FFmpeg Konvertierung fehlgeschlagen: "
                        f"{_sanitize_ffmpeg_error(stderr_text)}"
                    )

            if should_stop is not None and should_stop():
                raise RuntimeError("Auto-Ducking abgebrochen (User-Cancel)")

            if progress_cb:
                progress_cb(50, "Scipy Ducking laeuft...")

            result = self.create_ducked_audio_scipy(
                str(tmp_music), str(tmp_voice), output_path,
                progress_cb=None, should_stop=should_stop,
            )

            if progress_cb:
                progress_cb(100, "Auto-Ducking fertig")

            return result
        finally:
            tmp_music.unlink(missing_ok=True)
            tmp_voice.unlink(missing_ok=True)

    def create_ducked_audio_scipy(self, music_path: str, voice_path: str,
                                   output_path: str, progress_cb=None,
                                   should_stop=None) -> str:
        """Fallback: Scipy-basiertes Ducking wenn FFmpeg sidechaincompress fehlt.

        B-074: ``should_stop`` wird vor dem CPU-bound numpy-Loop geprueft.
        Granularitaet ist Pre-Loop — Cancel mitten im Compute-Loop
        wuerde tieferes Refactoring verlangen, aber Pre-Loop deckt
        den haeufigen Fall (Cancel waehrend FFmpeg-Konvertierung) ab.
        """
        if should_stop is not None and should_stop():
            raise RuntimeError("Auto-Ducking abgebrochen (User-Cancel)")
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

        # F-009: SR-Validierung — resample voice falls SR-Mismatch
        if voice_sr != music_sr:
            logger.warning(
                "[AutoDucker] SR-Mismatch: music=%d Hz, voice=%d Hz — resample voice auf %d Hz",
                music_sr, voice_sr, music_sr,
            )
            voice_data = librosa.resample(voice_data, orig_sr=voice_sr, target_sr=music_sr)

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

        # Finale Bounds-Pruefung
        mixed = np.clip(mixed, -1.0, 1.0)

        # A-01 Fix: Speichern als 32-bit float WAV (kein Int16-Quantisierungsrauschen)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), mixed, music_sr, subtype='FLOAT')

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
    # B-501: Dateien laenger als BLOCK_SEC werden blockweise geladen und
    # analysiert statt komplett in den RAM (3h-Mix @22050Hz mono float32 +
    # volle STFT waren mehrere GB RAM-Peak). 600s-Block ≈ 53 MB Audio +
    # ~210 MB STFT — danach wird der Block freigegeben.
    BLOCK_SEC = 600.0

    def _band_masks(self):
        """Boolesche Frequenz-Bin-Masken fuer Low/Mid/High (Raster SR/N_FFT)."""
        freqs = librosa.fft_frequencies(sr=self.SR, n_fft=self.N_FFT)
        low_mask = freqs <= self.LOW_MAX
        mid_mask = (freqs > self.LOW_MAX) & (freqs <= self.MID_MAX)
        high_mask = freqs > self.MID_MAX
        return low_mask, mid_mask, high_mask

    def _band_energies(self, y, center: bool = True):
        """STFT eines Signal-Abschnitts → mittlere Magnitude pro Band und Frame.

        center=False im Chunked-Pfad: Frames liegen exakt auf dem globalen
        Hop-Raster, kein Zero-Padding pro Block → keine Pad-Artefakte an
        Blockgrenzen. Single-Pass behaelt das bisherige center=True.
        """
        S = np.abs(librosa.stft(y, n_fft=self.N_FFT, hop_length=self.HOP_LENGTH,
                                center=center))
        low_mask, mid_mask, high_mask = self._band_masks()
        band_low = np.mean(S[low_mask, :], axis=0)
        band_mid = np.mean(S[mid_mask, :], axis=0)
        band_high = np.mean(S[high_mask, :], axis=0)
        return band_low, band_mid, band_high

    def _analyze_chunked(self, file_path: str, duration: float, progress_cb=None):
        """B-501: Blockweise Band-Analyse fuer lange Dateien (RAM-Schutz).

        Laedt BLOCK_SEC-Bloecke via ``librosa.load(offset=..., duration=...)``,
        rechnet pro Block STFT-Band-Energien und haengt sie an. Ein Carry-
        Puffer (Rest-Samples, die kein volles Frame mehr fuellen) wandert in
        den naechsten Block, damit das Frame-Raster ohne Luecke durchlaeuft.
        Der finale Carry-Rest (< N_FFT Samples ≈ 93 ms) wird verworfen.

        WICHTIG: Hier wird NICHT normalisiert — Normalisierung erfolgt global
        in analyze() nach der Block-Schleife. Pro-Block-Normalisierung wuerde
        sichtbare Spruenge an Blockgrenzen erzeugen.

        Bekannte Einschraenkung (nur dokumentiert, siehe B-501): MP3 ohne
        soundfile-Support faellt in librosa auf audioread zurueck, das bei
        offset-Loads jeweils vom Dateianfang dekodiert (O(n²) ueber alle
        Bloecke). WAV/FLAC seeken sample-genau.
        """
        low_parts, mid_parts, high_parts = [], [], []
        carry = np.zeros(0, dtype=np.float32)
        n_blocks = max(1, int(np.ceil(duration / self.BLOCK_SEC)))
        block_idx = 0
        block_start = 0.0
        while block_start < duration:
            y_block, _ = librosa.load(
                file_path, sr=self.SR, mono=True,
                offset=block_start, duration=self.BLOCK_SEC,
            )
            block_start += self.BLOCK_SEC
            block_idx += 1
            if y_block.size == 0:
                break
            y_proc = np.concatenate([carry, y_block]) if carry.size else y_block
            del y_block
            if y_proc.size < self.N_FFT:
                carry = y_proc
                continue
            band_low, band_mid, band_high = self._band_energies(y_proc, center=False)
            n_frames = int(band_low.shape[0])
            consumed = n_frames * self.HOP_LENGTH
            carry = np.array(y_proc[consumed:], dtype=np.float32, copy=True)
            del y_proc
            low_parts.append(band_low)
            mid_parts.append(band_mid)
            high_parts.append(band_high)
            gc.collect()
            if progress_cb:
                pct = 5 + int(70 * min(1.0, block_idx / n_blocks))
                progress_cb(pct, f"STFT Block {block_idx}/{n_blocks}...")
        if not low_parts:
            empty = np.zeros(0, dtype=np.float32)
            return empty, empty.copy(), empty.copy()
        return (
            np.concatenate(low_parts),
            np.concatenate(mid_parts),
            np.concatenate(high_parts),
        )

    def analyze(self, file_path: str, progress_cb=None) -> dict:
        """Berechnet Frequenzband-Amplituden (3-Band-Waveform).

        B-501: Dateien laenger als BLOCK_SEC (600 s) werden blockweise
        verarbeitet (konstanter RAM-Peak statt Full-Load + Voll-STFT).
        BPM/Beatgrid berechnet diese Methode NICHT mehr — das macht
        ausschliesslich BeatAnalysisService (beat_this). Das fruehere
        ``librosa.beat.beat_track`` ueber den ganzen Mix war ungenutzt.

        Returns dict mit:
            band_low:  list[float]   Normalisierte Bass-Amplituden [0..1]
            band_mid:  list[float]   Normalisierte Mitten-Amplituden [0..1]
            band_high: list[float]   Normalisierte Höhen-Amplituden [0..1]
            num_samples: int         Anzahl der Zeitschritte
            duration: float          Track-Dauer in Sekunden
        """
        if progress_cb:
            progress_cb(0, "Lade Audio...")

        # B-501: Dauer vorab ohne Full-Load ermitteln (Header/Stream-Scan)
        duration = float(librosa.get_duration(path=file_path))

        if duration > self.BLOCK_SEC:
            band_low, band_mid, band_high = self._analyze_chunked(
                file_path, duration, progress_cb=progress_cb,
            )
        else:
            # Bestehender Single-Pass fuer kurze Dateien (≤ BLOCK_SEC)
            y, _sr = librosa.load(file_path, sr=self.SR, mono=True)
            if progress_cb:
                progress_cb(20, "STFT Frequenzanalyse...")
            band_low, band_mid, band_high = self._band_energies(y, center=True)
            del y

        # Normalisierung: GLOBAL ueber die gesamte Datei auf [0..1] (Peak=1.0).
        # B-501: zwingend NACH der Block-Schleife — pro Block normalisieren
        # wuerde jeden Block gegen sein eigenes Maximum skalieren und sichtbare
        # Spruenge an Blockgrenzen erzeugen.
        def _normalize(arr):
            peak = arr.max() if arr.size else 0.0
            if peak > 0:
                return arr / peak
            return arr

        band_low = _normalize(band_low)
        band_mid = _normalize(band_mid)
        band_high = _normalize(band_high)

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
        # B-501: "bpm" und "beat_positions" entfernt — BPM/Beatgrid liefert
        # ausschliesslich BeatAnalysisService; Aufrufer nutzen .get()-Defaults.
        result = {
            "band_low": [round(float(v), 4) for v in band_low_store],
            "band_mid": [round(float(v), 4) for v in band_mid_store],
            "band_high": [round(float(v), 4) for v in band_high_store],
            "num_samples": store_samples,
            "duration": round(duration, 3),
        }

        if progress_cb:
            progress_cb(100, "Frequenzanalyse abgeschlossen")

        return result

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und speichert die 3-Band-Waveform in der DB.

        B-501: Schreibt NUR WaveformData + track.duration. BPM und Beatgrid
        schreibt ausschliesslich BeatAnalysisService (beat_this) — ein in der
        DB vorhandener BPM-Wert wird lediglich fuer die UI-Anzeige in das
        Ergebnis-Dict durchgereicht ("bpm"-Key fehlt, wenn kein BPM in DB).
        """
        import time as _time

        with nullpool_session() as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        result = self.analyze(file_path, progress_cb=progress_cb)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with nullpool_session() as session:
                    track = session.get(AudioTrack, track_id)
                    if track is None:
                        raise ValueError(f"AudioTrack {track_id} nach Frequenzanalyse nicht mehr gefunden")

                    # B-501: FrequencyAnalyzer berechnet/schreibt kein BPM mehr
                    # (totes librosa.beat.beat_track entfernt; ersetzt J-01).
                    # BPM/Beatgrid schreibt ausschliesslich BeatAnalysisService.
                    # Vorhandenen DB-Wert nur fuer die UI-Anzeige durchreichen.
                    if track.bpm is not None:
                        result["bpm"] = float(track.bpm)
                    track.duration = result["duration"]

                    # DB-07 Fix: Expliziter Query-Check gegen Duplikate
                    existing_wd = track.waveform_data or session.query(WaveformData).filter_by(
                        audio_track_id=track_id
                    ).first()

                    if existing_wd:
                        existing_wd.num_samples = result["num_samples"]
                        existing_wd.duration = result["duration"]
                        existing_wd.band_low = result["band_low"]
                        existing_wd.band_mid = result["band_mid"]
                        existing_wd.band_high = result["band_high"]
                    else:
                        wd = WaveformData(
                            audio_track_id=track_id,
                            num_samples=result["num_samples"],
                            duration=result["duration"],
                            band_low=result["band_low"],
                            band_mid=result["band_mid"],
                            band_high=result["band_high"],
                        )
                        session.add(wd)

                    session.commit()
                break  # Erfolg
            except Exception as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    # B-073: exponential backoff + random jitter (0.5-1.5x base)
                    # statt linearer 2/4/6s — verhindert Thundering-Herd wenn
                    # mehrere Analysen parallel auf denselben Lock retrien.
                    import random as _random
                    base_wait = 2 ** attempt
                    jitter = _random.uniform(0.5, 1.5)
                    wait = base_wait * jitter
                    logger.warning(
                        "[FrequencyAnalyzer] DB locked bei Waveform-Write, Retry %d/%d (warte %.2fs)...",
                        attempt + 1, max_retries, wait,
                    )
                    _time.sleep(wait)
                else:
                    raise

        try:
            from services.pacing_service import invalidate_pacing_caches
            invalidate_pacing_caches()
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning("invalidate_pacing_caches() fehlgeschlagen: %s", e)

        return result
