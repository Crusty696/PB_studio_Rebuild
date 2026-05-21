"""AI Audio Service: Demucs Stem Separation + Auto-Ducking + Rekordbox Frequency Analysis."""

import gc
import json
import logging
import subprocess
import sys
import tempfile
from functools import wraps
from pathlib import Path

from services.errors import CUDAOutOfMemoryError
from services.audio_constants import clamp_bpm
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
from database import engine, AudioTrack, WaveformData, nullpool_session

from services.model_manager import ModelManager, oom_recovery

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


def _sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages — strip full paths."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def _load_audio_for_stem_separation(
    src: Path,
    torchaudio_module,
    target_sr: int,
):
    """Load audio for Demucs, falling back to FFmpeg for containers unsupported by libsndfile."""
    try:
        return torchaudio_module.load(str(src))
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
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
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
            waveform, sr = torchaudio_module.load(str(tmp_wav_path))
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
            sr,
            waveform.shape[1],
        )
        return waveform, sr

# Chunk-Dauer in Sekunden fuer VRAM-schonendes Processing
CHUNK_SECONDS = 30
# Overlap in Sekunden um Artefakte an Chunk-Grenzen zu vermeiden
OVERLAP_SECONDS = 2


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
    def separate(self, file_path: str, model: str = "htdemucs_ft",
                 progress_cb=None, should_stop=None) -> dict[str, str]:
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

        if progress_cb:
            progress_cb(10, "Lade Audio-Datei...")

        # ── 4. Audio laden ──
        # Demucs erwartet die Samplerate des Modells (typisch 44100 Hz).
        # Stems werden in model_sr gespeichert. Die Pacing-Pipeline (pacing_service.py)
        # laedt Stems spaeter mit librosa (Default 22050 Hz) — das Downsampling ist beabsichtigt.
        model_sr = demucs_model.samplerate
        waveform, sr = _load_audio_for_stem_separation(src, torchaudio, model_sr)
        if sr != model_sr:
            waveform = torchaudio.functional.resample(waveform, sr, model_sr)
            sr = model_sr

        # Stereo sicherstellen (Demucs erwartet 2 Kanaele)
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        elif waveform.shape[0] > 2:
            waveform = waveform[:2]

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
        if estimated_ram_gb > 8.0:
            logger.warning(
                "[StemSeparator] WARNUNG: Grosser Akkumulator — %.1f GB RAM geschaetzt fuer "
                "%.0f min Audio. Behalte float32 fuer maximale Qualitaet.",
                estimated_ram_gb, total_samples / sr / 60,
            )
            if progress_cb:
                progress_cb(15, f"Hinweis: ~{estimated_ram_gb:.0f} GB RAM fuer Akkumulator benoetigt")
        elif estimated_ram_gb > 3.0:
            logger.info(
                "[StemSeparator] Akkumulator: %.1f GB RAM geschaetzt fuer %.0f min Audio (float32).",
                estimated_ram_gb, total_samples / sr / 60,
            )

        # Ergebnis-Tensor fuer alle Stems (Crossfade-Akkumulator) — immer float32
        result_stems = torch.zeros(num_sources, waveform.shape[0], total_samples, dtype=torch.float32)
        weight_sum = torch.zeros(1, total_samples, dtype=torch.float32)

        # B-601 Fix: GPU-Code in try/finally um ANY Exception zu handhaben
        try:
            for i in range(num_chunks):
                # F-008 Fix: Abbruch-Check
                if should_stop and should_stop():
                    logger.info("[StemSeparator] Abbruch durch Benutzer.")
                    break

                start = i * step_samples
                end = min(start + chunk_samples, total_samples)
                chunk = waveform[:, start:end]

                logger.info(f"[StemSeparator] Verarbeite Chunk {i + 1}/{num_chunks} "
                      f"auf {device.type.upper()} "
                      f"({start / sr:.1f}s - {end / sr:.1f}s)...")

                # Chunk auf GPU, Batch-Dimension hinzufuegen: (1, channels, samples)
                chunk_gpu = chunk.unsqueeze(0).to(device)

                # D-04 Fix: try/except um apply_model() — bei OOM Chunk halbieren und einmal retrien
                with torch.no_grad():
                    try:
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
                    except RuntimeError:
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
                        except RuntimeError:
                            torch.cuda.empty_cache()
                            gc.collect()
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
                for s in range(num_sources):
                    weighted = estimates_cpu[s, :, :chunk_len] * fade.unsqueeze(0)
                    result_stems[s, :, start:end] += weighted
                weight_sum[0, start:end] += fade

                # ── VRAM sofort freigeben ──
                # Sicheres Loeschen: chunk_gpu kann bei OOM-Retry bereits geloescht sein
                chunk_gpu = None
                estimates = None
                estimates_cpu = None
                gc.collect()
                torch.cuda.empty_cache()

                # Progress: 15% bis 85% fuer Chunk-Processing
                if progress_cb:
                    pct = 15 + int(70 * (i + 1) / num_chunks)
                    progress_cb(pct, f"Chunk {i + 1}/{num_chunks} fertig")

            # Normalisierung durch Gewichtssumme (Crossfade — AUSSERHALB der for-Schleife)
            weight_sum = weight_sum.clamp(min=1e-8)
            for s in range(num_sources):
                result_stems[s] /= weight_sum
        finally:
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
        stem_dir = _get_stems_dir() / model / src.stem
        stem_dir.mkdir(parents=True, exist_ok=True)

        # A-02: result_stems ist bereits float32 (kein float16-Pfad mehr)

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
                stems = self.separate(file_path, progress_cb=progress_cb)
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

    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

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

                    # J-01 Fix: BPM nur setzen wenn noch kein BPM vorhanden ist.
                    # In der Komplett-Analyse laeuft BeatAnalysisService (beat_this) zuerst
                    # und liefert praezisere BPM. FrequencyAnalyzer (librosa) laeuft danach
                    # und soll den genaueren beat_this-Wert nicht ueberschreiben.
                    if track.bpm is None:
                        track.bpm = clamp_bpm(result["bpm"])
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
