"""AV Pacing Service — Visuelle Steuerungs-Metriken aus Audio (audio-analysis-v2).

4 Metriken auf dem Original-Mix, als Timeline-Sequenz fuer Video-Steuerung:
- spectral_centroid: Filter-Sweeps -> Bildhelligkeit / Partikelgeschwindigkeit
- spectral_flux:     abrupte Sound-Wechsel -> harte Schnitte / Glitch-Effekte
- stereo_width:      Mid/Side-Verhaeltnis -> Kamera-Weite / Spiegelungseffekte
- percussive_ratio:  HPSS perkussiv / total -> Stroboskop vs Morph

Streaming-Pflicht: nie >1 Chunk (60s default) im RAM. Geeignet fuer 4h-Mixe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

try:
    import librosa  # type: ignore
    _HAS_LIBROSA = True
except ImportError:
    librosa = None  # type: ignore[assignment]
    _HAS_LIBROSA = False

try:
    import soundfile as sf  # type: ignore
    _HAS_SOUNDFILE = True
except ImportError:
    sf = None  # type: ignore[assignment]
    _HAS_SOUNDFILE = False

from services.audio_constants import (
    DEFAULT_SR,
    AV_PACING_HOP_SEC,
    AV_PACING_FRAME_SEC,
    AV_PACING_STREAM_CHUNK_SEC,
)

log = logging.getLogger(__name__)


@dataclass
class AVPacingResult:
    """Timeline-Sequenz der AV-Pacing-Metriken (gleiche Laenge, gleicher Hop)."""
    sample_rate: int = DEFAULT_SR
    hop_sec: float = AV_PACING_HOP_SEC
    times_sec: list[float] = field(default_factory=list)
    spectral_centroid: list[float] = field(default_factory=list)   # Hz
    spectral_flux: list[float] = field(default_factory=list)        # 0..n
    stereo_width: list[float] = field(default_factory=list)         # 0..1 (Side/(Mid+Side))
    percussive_ratio: list[float] = field(default_factory=list)     # 0..1
    # RMS-Energie pro Hop, roh (nicht normiert). Faellt im selben Stream ab —
    # kein zusaetzliches Audio-Laden. Konsument: services/pacing/audio_video_curves
    # (Energy-Match RMS-Kurve vs. Clip-Motion-Kurve, 100ms-Grid = AV_PACING_HOP_SEC).
    rms: list[float] = field(default_factory=list)                  # 0..n


class AVPacingService:
    """CPU-Service: librosa-basierte Stream-Analyse fuer AV-Pacing."""

    def analyze(
        self,
        file_path: str,
        sr: int | None = None,
        chunk_sec: float = AV_PACING_STREAM_CHUNK_SEC,
        should_stop=None,
        hpss_margin: float = 2.0,
        overlap_sec: float = 4.0,
    ) -> AVPacingResult:
        """Analysiert Audio-Datei und liefert 4 AV-Pacing-Timeline-Metriken.

        audio-analysis-v2 Iteration 3 (P2-Fix #3 voll): **Overlap-Add Streaming.**
        Jeder Chunk wird mit ``overlap_sec`` Vor-Kontext vom vorigen Chunk
        erweitert. HPSS-Median-Filter und STFT sehen damit stabilen Kontext
        ueber Chunk-Grenzen hinweg; Hops aus dem Vor-Kontext werden verworfen.
        Eliminiert HPSS-Diskontinuitaeten und ersetzt P2-Fix #4 (erste-Hop-Drop).

        audio-analysis-v2 P2-Fix #5: Verwendet die **native** Sample-Rate der
        Datei (kein Per-Chunk-Resample).

        Args:
            file_path: Pfad zur Audio-Datei.
            sr: deprecated — native SR wird verwendet.
            chunk_sec: Stream-Chunk-Dauer in Sekunden.
            should_stop: optional Callable[[], bool] fuer Cancellation.
            hpss_margin: librosa.effects.hpss margin (Default 2.0).
            overlap_sec: Vor-Kontext-Dauer pro Folge-Chunk (Default 4.0s) —
                trade-off Median-Filter-Stabilitaet vs Compute-Overhead.
        """
        if not _HAS_LIBROSA or not _HAS_SOUNDFILE:
            raise RuntimeError(
                "AVPacingService requires librosa + soundfile. "
                "Install: pip install librosa soundfile"
            )

        # Native SR ermitteln (kein Resample)
        with sf.SoundFile(file_path) as f:
            native_sr = f.samplerate
        if sr is not None and sr != native_sr:
            log.info("AVPacingService: native SR=%d (sr=%d arg ignored, P2-Fix #5)", native_sr, sr)
        sr = native_sr

        hop_samples = max(1, int(AV_PACING_HOP_SEC * sr))
        n_fft = self._next_pow2(int(AV_PACING_FRAME_SEC * sr))
        overlap_samples = max(0, int(overlap_sec * sr))
        # Anzahl Hops im Overlap-Bereich (zu verwerfen am Anfang jedes Folge-Chunks)
        overlap_hops = max(0, overlap_samples // hop_samples) if overlap_samples > 0 else 0

        result = AVPacingResult(sample_rate=sr, hop_sec=AV_PACING_HOP_SEC)
        prev_mag: np.ndarray | None = None
        prev_tail_mono: np.ndarray = np.zeros(0, dtype=np.float32)
        prev_tail_stereo: np.ndarray | None = None
        global_sample_at_new_start = 0   # absolute Audio-Position am Anfang von new_mono
        last_emitted_sample = -1         # zuletzt emittiertes Sample (vermeidet Duplikate ueber Chunk-Grenzen)
        chunk_idx = 0

        for new_mono, new_stereo in self._stream_chunks_native(file_path, chunk_sec):
            if should_stop is not None and should_stop():
                log.info("AVPacingService.analyze: should_stop() True -> abort at chunk %d", chunk_idx)
                break

            # Erweiterter Chunk = prev_tail + new (P2-Fix #3 Overlap-Add)
            if chunk_idx == 0 or prev_tail_mono.size == 0:
                ext_mono = new_mono
                ext_stereo = new_stereo
                ext_start_sample = global_sample_at_new_start
            else:
                ext_mono = np.concatenate([prev_tail_mono, new_mono])
                if new_stereo is not None and prev_tail_stereo is not None and prev_tail_stereo.shape[1] == new_stereo.shape[1]:
                    ext_stereo = np.concatenate([prev_tail_stereo, new_stereo], axis=0)
                else:
                    ext_stereo = new_stereo
                ext_start_sample = global_sample_at_new_start - prev_tail_mono.shape[0]

            n_ext = len(ext_mono)
            if n_ext < n_fft:
                ext_mono = np.pad(ext_mono, (0, n_fft - n_ext))
                if ext_stereo is not None:
                    ext_stereo = np.pad(ext_stereo, ((0, n_fft - ext_stereo.shape[0]), (0, 0)))

            # Features auf erweitertem Chunk
            cent = librosa.feature.spectral_centroid(
                y=ext_mono, sr=sr, n_fft=n_fft, hop_length=hop_samples,
            )[0]
            stft = np.abs(librosa.stft(ext_mono, n_fft=n_fft, hop_length=hop_samples))
            flux = self._spectral_flux_seq(stft, prev_mag)
            if stft.shape[1] > 0:
                prev_mag = stft[:, -1].copy()
            try:
                harm, perc = librosa.effects.hpss(ext_mono, margin=hpss_margin)
                perc_ratio = self._chunked_ratio(perc, harm, hop_samples, len(cent))
            except Exception as e:  # noqa: BLE001
                log.warning("HPSS failed on chunk: %s -> zeros", e)
                perc_ratio = np.zeros(len(cent), dtype=np.float32)
            if ext_stereo is not None and ext_stereo.shape[1] >= 2:
                sw = self._stereo_width_seq(ext_stereo, hop_samples, len(cent))
            else:
                sw = np.zeros(len(cent), dtype=np.float32)
            # RMS auf demselben Hop-Raster wie cent — laeuft im bestehenden
            # Stream mit, kostet kein zusaetzliches Audio-Laden. center=True wie
            # bei den librosa-Feature-Defaults oben, damit die Frame-Anzahl zu
            # cent passt.
            try:
                rms_seq = librosa.feature.rms(
                    y=ext_mono, frame_length=n_fft, hop_length=hop_samples,
                )[0]
            except Exception as e:  # noqa: BLE001
                log.warning("RMS failed on chunk: %s -> zeros", e)
                rms_seq = np.zeros(len(cent), dtype=np.float32)

            # Append: nur frames mit absolute_sample > last_emitted_sample
            for i in range(len(cent)):
                abs_sample = ext_start_sample + i * hop_samples
                if abs_sample <= last_emitted_sample:
                    continue
                t = abs_sample / sr
                result.times_sec.append(t)
                result.spectral_centroid.append(float(cent[i]))
                result.spectral_flux.append(float(flux[i]) if i < len(flux) else 0.0)
                result.percussive_ratio.append(float(perc_ratio[i]) if i < len(perc_ratio) else 0.0)
                result.stereo_width.append(float(sw[i]) if i < len(sw) else 0.0)
                result.rms.append(float(rms_seq[i]) if i < len(rms_seq) else 0.0)
                last_emitted_sample = abs_sample

            # Tail vom Ende des erweiterten Chunks bewahren
            if overlap_samples > 0 and len(ext_mono) >= overlap_samples:
                prev_tail_mono = ext_mono[-overlap_samples:].astype(np.float32, copy=True)
                if ext_stereo is not None:
                    prev_tail_stereo = ext_stereo[-overlap_samples:].astype(np.float32, copy=True)
                else:
                    prev_tail_stereo = None
            else:
                # overlap_sec=0 -> kein prev_tail bewahren (sonst Doppel-Read)
                prev_tail_mono = np.zeros(0, dtype=np.float32)
                prev_tail_stereo = None

            global_sample_at_new_start += len(new_mono)
            chunk_idx += 1

        return result

    # ─────────────────── helpers ───────────────────

    def _stream_chunks_native(
        self,
        file_path: str,
        chunk_sec: float,
    ) -> Iterator[tuple[np.ndarray, np.ndarray | None]]:
        """audio-analysis-v2 P2-Fix #5: Streamt Datei chunk-weise IN NATIVE SR.

        Kein Per-Chunk-Resample mehr -> keine Filter-State-Klick-Artefakte
        an Chunk-Grenzen. Mono-Downmix erfolgt sample-weise (informationsneutral).

        Liefert (mono, stereo) pro Chunk. stereo == None bei Mono-Datei.
        """
        with sf.SoundFile(file_path) as f:
            file_sr = f.samplerate
            channels = f.channels
            frames_per_chunk = max(1, int(chunk_sec * file_sr))
            while True:
                data = f.read(frames_per_chunk, dtype="float32", always_2d=True)
                if data.shape[0] == 0:
                    return
                stereo = data if channels >= 2 else None
                mono = data.mean(axis=1) if channels > 1 else data[:, 0]
                yield mono.astype(np.float32, copy=False), (
                    stereo.astype(np.float32, copy=False) if stereo is not None else None
                )

    @staticmethod
    def _spectral_flux_seq(stft: np.ndarray, prev_mag: np.ndarray | None) -> np.ndarray:
        """L2-Norm der positiven Magnitude-Differenz pro Hop."""
        if stft.shape[1] == 0:
            return np.zeros(0, dtype=np.float32)
        # Erste Spalte gegen prev_mag
        if prev_mag is None or prev_mag.shape[0] != stft.shape[0]:
            prev_mag = stft[:, 0]
        diffs = np.diff(np.concatenate([prev_mag[:, None], stft], axis=1), axis=1)
        diffs = np.maximum(diffs, 0.0)
        return np.linalg.norm(diffs, axis=0).astype(np.float32)

    @staticmethod
    def _chunked_ratio(
        perc: np.ndarray,
        harm: np.ndarray,
        hop_samples: int,
        n_out: int,
    ) -> np.ndarray:
        """percussive RMS / (perc+harm) RMS pro Hop. n_out clampt Laenge."""
        out = np.zeros(n_out, dtype=np.float32)
        for i in range(n_out):
            s = i * hop_samples
            e = min(len(perc), s + hop_samples)
            if e <= s:
                continue
            p = float(np.sqrt(np.mean(perc[s:e] ** 2)))
            h = float(np.sqrt(np.mean(harm[s:e] ** 2)))
            denom = p + h
            out[i] = p / denom if denom > 1e-9 else 0.0
        return out

    @staticmethod
    def _stereo_width_seq(
        stereo: np.ndarray,
        hop_samples: int,
        n_out: int,
    ) -> np.ndarray:
        """Side-Energy / (Mid+Side)-Energy pro Hop. 0=Mono, ~1=stark Side."""
        out = np.zeros(n_out, dtype=np.float32)
        if stereo.shape[1] < 2:
            return out
        L = stereo[:, 0]
        R = stereo[:, 1]
        mid = 0.5 * (L + R)
        side = 0.5 * (L - R)
        for i in range(n_out):
            s = i * hop_samples
            e = min(len(mid), s + hop_samples)
            if e <= s:
                continue
            mid_e = float(np.sqrt(np.mean(mid[s:e] ** 2)))
            side_e = float(np.sqrt(np.mean(side[s:e] ** 2)))
            denom = mid_e + side_e
            out[i] = side_e / denom if denom > 1e-9 else 0.0
        return out

    @staticmethod
    def _next_pow2(n: int) -> int:
        n = max(1, n)
        p = 1
        while p < n:
            p <<= 1
        return p
