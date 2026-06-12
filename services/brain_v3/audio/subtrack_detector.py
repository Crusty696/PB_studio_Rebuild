"""Brain V3 — SubtrackDetector (Plan-Doc 06 Phase 1, Block-4-Pipeline).

Erkennt Sub-Track-Grenzen in einem DJ-Mix durch Fusion von 4 Signalen:

    S1: Foote-Novelty           (gewicht 0.35) — librosa.segment + scipy
    S2: Stem-Aktivitaet         (gewicht 0.30) — RMS-Spruenge in Stems
    S3: Tempo-Drift             (gewicht 0.20) — librosa.beat sliding-window
    S4: Spectral-Flux-Cluster   (gewicht 0.15) — librosa.onset Aggregat

Fusion: gewichtete Summe → Peak-Picking mit min_distance=60 s, adaptive
Threshold (mean + 1.5 * std).

Fallback (Plan-Spec): 0 Boundaries gefunden → Mix wird als 1 Sub-Track
behandelt. Das ist keine Fehler-Situation, sondern bewusste Behandlung
fuer seamless mixes (Tech-House, Trance).

CPU-only (librosa + scipy + numpy). Kein GPU-Bedarf, deshalb kein
GPULockMiddleware noetig.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from services.brain_v3.schemas.audio import (
    SubtrackSegment, SubtrackDetectionResult,
)

logger = logging.getLogger(__name__)

# Plan-Doc 06 Phase 1 — Default-Parameter
DEFAULT_FUSION_WEIGHTS: dict[str, float] = {
    "foote": 0.35,
    "stem": 0.30,
    "tempo": 0.20,
    "spectral": 0.15,
}
MIN_DISTANCE_SECONDS = 60.0  # Plan-Doc 06: min_distance=60s
ADAPTIVE_THRESHOLD_K = 1.5    # Threshold = mean + K * std
DEFAULT_HOP_SECONDS = 1.0     # 1-Hz-Sampling der Curves intern
# B-510: feste Analyse-SR statt nativer SR (sr=None lud 44.1/48k -> doppelter
# RAM bei 3h-Mixes). 22050 Hz reicht fuer MFCC/Tempo/Flux-Features vollstaendig.
TARGET_SR = 22050


class _DetectionAborted(Exception):
    """B-510: internes Signal fuer sauberen Abbruch via should_stop()."""


@dataclass(frozen=True)
class _Hop:
    """Fester Sampling-Raster fuer alle 4 Signale, danach werden sie addiert."""
    sr: int
    hop_seconds: float

    @property
    def hop_samples(self) -> int:
        return int(self.sr * self.hop_seconds)


class SubtrackDetector:
    """4-Signal-Fusion fuer Sub-Track-Detektion.

    Usage:
        det = SubtrackDetector()
        result = det.detect(audio_path, audio_hash="...")

    Stems sind optional — wenn None, wird S2 mit Null-Curve gefuettert
    und Gewichte werden re-normalisiert.
    """

    def __init__(
        self,
        fusion_weights: Optional[dict[str, float]] = None,
        min_distance_seconds: float = MIN_DISTANCE_SECONDS,
        adaptive_threshold_k: float = ADAPTIVE_THRESHOLD_K,
        hop_seconds: float = DEFAULT_HOP_SECONDS,
    ) -> None:
        self.weights = dict(fusion_weights or DEFAULT_FUSION_WEIGHTS)
        self.min_distance_seconds = min_distance_seconds
        self.adaptive_threshold_k = adaptive_threshold_k
        self.hop_seconds = hop_seconds
        # Lazy librosa import — nur wenn detect() laeuft
        self._librosa = None
        self._scipy_signal = None

    def _import_deps(self):
        if self._librosa is None:
            import librosa  # type: ignore
            self._librosa = librosa
        if self._scipy_signal is None:
            from scipy import signal  # type: ignore
            self._scipy_signal = signal
        return self._librosa, self._scipy_signal

    def detect(
        self,
        audio_path: Path | str,
        audio_hash: str,
        stems_paths: Optional[dict[str, Path]] = None,
        progress_cb=None,
        should_stop=None,
    ) -> Optional[SubtrackDetectionResult]:
        """Fuehrt die 4-Signal-Pipeline aus.

        Args:
            audio_path: Pfad zur Mix-Datei (mp3, wav, flac, ...).
            audio_hash: sha256 der Mix-Datei (von services.brain_v3.hashing).
                        Wird unverarbeitet ins Result kopiert (fuer Caching).
            stems_paths: Optional dict {stem_name: file_path} (z.B. von Demucs).
                         Wenn None: S2-Stem-Activity nutzt Null-Curve, S2-Gewicht
                         wird auf andere Signale re-normalisiert.
            progress_cb: Optional callable(pct: int, msg: str) — B-510.
            should_stop: Optional callable() -> bool — B-510. Liefert es True,
                         bricht detect() sauber ab und gibt None zurueck
                         (kein Teilergebnis; aktuelle Aufrufer — Tests und
                         Spike-Skripte — reichen should_stop nicht durch).

        Returns:
            SubtrackDetectionResult mit Segmenten oder Fallback (1 Segment);
            None bei Abbruch via should_stop.
        """
        librosa, _signal = self._import_deps()
        logger.info("SubtrackDetector.detect start: %s", audio_path)

        # B-510: feste 22050 Hz statt nativer SR (halbiert RAM bei 44.1/48k-Mixes)
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
        duration = float(len(y) / sr)
        if duration <= 0:
            raise ValueError(f"Audio-Datei leer: {audio_path}")

        hop = _Hop(sr=sr, hop_seconds=self.hop_seconds)

        if progress_cb:
            progress_cb(10, "Audio geladen")

        # Pipeline (B-510: abbrechbar via should_stop)
        try:
            self._check_stop(should_stop)
            s1 = self._signal_foote_novelty(y, sr, hop)
            if progress_cb:
                progress_cb(35, "Foote-Novelty berechnet")
            self._check_stop(should_stop)
            s2 = self._signal_stem_activity(
                stems_paths, sr, hop, n_samples=len(s1), should_stop=should_stop,
            )
            if progress_cb:
                progress_cb(45, "Stem-Aktivitaet berechnet")
            self._check_stop(should_stop)
            s3 = self._signal_tempo_drift(
                y, sr, hop, n_samples=len(s1),
                progress_cb=progress_cb, should_stop=should_stop,
            )
            if progress_cb:
                progress_cb(85, "Tempo-Drift berechnet")
            self._check_stop(should_stop)
            s4 = self._signal_spectral_flux(y, sr, hop, n_samples=len(s1))
            if progress_cb:
                progress_cb(95, "Spectral-Flux berechnet")
        except _DetectionAborted:
            logger.info("SubtrackDetector: Abbruch via should_stop() — return None.")
            return None

        # Re-normalisiere Gewichte falls S2 fehlt
        weights = self._effective_weights(stems_used=stems_paths is not None)

        fused = (
            weights["foote"] * s1
            + weights["stem"] * s2
            + weights["tempo"] * s3
            + weights["spectral"] * s4
        )

        boundaries_seconds = self._peak_pick(
            fused, hop_seconds=self.hop_seconds, duration=duration,
        )
        logger.info(
            "SubtrackDetector: %d boundaries gefunden bei [%s] (s)",
            len(boundaries_seconds),
            ", ".join(f"{b:.1f}" for b in boundaries_seconds[:10]),
        )

        segments = self._boundaries_to_segments(
            boundaries_seconds, duration, fused, hop_seconds=self.hop_seconds,
        )
        fallback_used = len(segments) == 1 and len(boundaries_seconds) == 0
        if fallback_used:
            logger.info("SubtrackDetector: 0 Boundaries → Fallback (Mix als 1 Sub-Track).")

        if progress_cb:
            progress_cb(100, "Subtrack-Detektion abgeschlossen")

        return SubtrackDetectionResult(
            audio_hash=audio_hash,
            duration_seconds=duration,
            n_segments=len(segments),
            segments=segments,
            fusion_weights=weights,
            fallback_used=fallback_used,
        )

    # ------------------------------------------------------------------
    # 4 Signale
    # ------------------------------------------------------------------
    @staticmethod
    def _check_stop(should_stop) -> None:
        """B-510: wirft _DetectionAborted wenn should_stop() True liefert."""
        if should_stop is not None and should_stop():
            raise _DetectionAborted()

    def _signal_foote_novelty(self, y: np.ndarray, sr: int, hop: _Hop) -> np.ndarray:
        """S1 — Foote-Novelty ueber MFCC-Self-Similarity."""
        librosa, _ = self._import_deps()
        # MFCC mit dem Detector-eigenen Hop berechnen
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=hop.hop_samples)
        # Recurrence-Matrix-basierte Novelty
        # librosa.segment.recurrence_matrix laeuft auf MFCC-Frames
        rec = librosa.segment.recurrence_matrix(
            mfcc, mode="affinity", sym=True,
        )
        # Foote-Kernel-Approximation: Diagonal-Differenz auf affinity matrix
        n = rec.shape[0]
        kernel_size = min(64, max(4, n // 32))
        novelty = self._foote_kernel_novelty(rec, kernel_size=kernel_size)
        return self._normalize(novelty)

    @staticmethod
    def _foote_kernel_novelty(rec: np.ndarray, kernel_size: int) -> np.ndarray:
        """Klassischer Foote-Kernel: Differenz zwischen +1/+1 und +1/-1 Quadranten.

        B-510: vektorisiert via Summed-Area-Table (Integralbild) statt purem
        Python-Doppelloop (O(n*k^2) -> O(n^2) Aufbau + O(n) Auswertung).
        Numerische Aequivalenz zum alten Loop: tests/test_services/
        test_brain_v3_subtrack_detector.py (_foote_novelty_reference).
        """
        n = rec.shape[0]
        novelty = np.zeros(n)
        k = int(kernel_size)
        if n < 2 * k + 1:
            return novelty
        # Slab-weise: SAT nur ueber (slab+2k)^2-Ausschnitt statt n^2 —
        # bei 3h-Mix (n=10800) sonst ~933 MB Zusatz-Transient.
        slab = 2048
        for i0 in range(k, n - k, slab):
            i1 = min(i0 + slab, n - k)
            r0 = i0 - k
            r1 = i1 + k  # exklusiv; alle Bloecke fuer i in [i0, i1) liegen darin
            sub = rec[r0:r1, r0:r1].astype(np.float64)
            m = sub.shape[0]
            # Integralbild mit Null-Rand: sat[r, c] = Summe von sub[:r, :c]
            sat = np.zeros((m + 1, m + 1), dtype=np.float64)
            sat[1:, 1:] = np.cumsum(np.cumsum(sub, axis=0), axis=1)
            idx = np.arange(i0, i1) - r0  # lokale Diagonal-Mittelpunkte

            def _block_sum(a0, a1, b0, b1):
                return sat[a1, b1] - sat[a0, b1] - sat[a1, b0] + sat[a0, b0]

            tl = _block_sum(idx - k, idx, idx - k, idx)
            br = _block_sum(idx, idx + k, idx, idx + k)
            tr = _block_sum(idx - k, idx, idx, idx + k)
            bl = _block_sum(idx, idx + k, idx - k, idx)
            novelty[i0:i1] = ((tl + br) - (tr + bl)) / float(k * k)
        return np.clip(novelty, 0, None)

    def _signal_stem_activity(
        self,
        stems_paths: Optional[dict[str, Path]],
        sr: int,
        hop: _Hop,
        n_samples: int,
        should_stop=None,
    ) -> np.ndarray:
        """S2 — RMS-Spruenge in Stems (Drum-In/Out, Bass-Drop, etc.).

        Wenn keine Stems vorhanden: Null-Curve. Gewicht wird in
        _effective_weights() re-normalisiert.
        B-510: Stems werden mit der festen Detector-SR (22050 via ``sr``)
        geladen statt nativ — 4 Full-Loads @ 44.1k entfallen.
        """
        if not stems_paths:
            return np.zeros(n_samples)
        librosa, _ = self._import_deps()
        rms_diff_total = np.zeros(n_samples)
        for stem_name, stem_path in stems_paths.items():
            self._check_stop(should_stop)
            try:
                y, _ = librosa.load(str(stem_path), sr=sr, mono=True)
                rms = librosa.feature.rms(y=y, hop_length=hop.hop_samples)[0]
                # Auf gleiche Laenge bringen
                rms_resampled = self._resize_to(rms, n_samples)
                rms_diff = np.abs(np.diff(rms_resampled, prepend=rms_resampled[0]))
                rms_diff_total += rms_diff
            except Exception as exc:
                logger.warning("Stem %s nicht ladbar: %s", stem_name, exc)
        return self._normalize(rms_diff_total)

    def _signal_tempo_drift(self, y: np.ndarray, sr: int, hop: _Hop,
                            n_samples: int, progress_cb=None,
                            should_stop=None) -> np.ndarray:
        """S3 — Sliding-Window Tempo-Drift via librosa.beat.tempo.

        Window 30 s, Step = hop_seconds. Tempo-Differenz zwischen Windows
        ist das Signal. B-510: teuerste Schleife der Pipeline — prueft
        should_stop pro Window und meldet Fortschritt (45..85 %).
        """
        librosa, _ = self._import_deps()
        win_seconds = 30.0
        win_samples = int(sr * win_seconds)
        step_samples = int(sr * self.hop_seconds)
        n_steps = max(1, (len(y) - win_samples) // step_samples + 1)

        # F-25 (B-357): the strided windows can leave up to one hop unanalyzed at
        # the end, so a DJ outro tempo change is missed. Add a final full-length
        # window anchored at the signal end when such a remainder exists.
        # _resize_to() below renormalizes the length, so the extra sample is safe.
        _last_start = (n_steps - 1) * step_samples
        _add_tail = len(y) >= win_samples and (len(y) - (_last_start + win_samples)) > 0
        total_steps = n_steps + (1 if _add_tail else 0)

        tempos = np.zeros(total_steps)
        _progress_every = max(1, total_steps // 20)
        for i in range(total_steps):
            self._check_stop(should_stop)
            if progress_cb and i % _progress_every == 0:
                pct = 45 + int(40 * i / max(1, total_steps))
                progress_cb(pct, f"Tempo-Drift Window {i + 1}/{total_steps}")
            if _add_tail and i == total_steps - 1:
                start = len(y) - win_samples
            else:
                start = i * step_samples
            window = y[start:start + win_samples]
            if len(window) < sr * 5:  # zu kurz fuer Beat-Tracking
                tempos[i] = tempos[i - 1] if i > 0 else 0.0
                continue
            try:
                # API-Wechsel librosa 0.10+: feature.rhythm.tempo statt beat.tempo.
                # rhythm ist Submodul, muss explizit importiert werden — sonst
                # bleibt die FutureWarning aktiv.
                try:
                    from librosa.feature.rhythm import tempo as _tempo_fn
                except (ImportError, AttributeError):
                    _tempo_fn = librosa.beat.tempo
                t = _tempo_fn(y=window, sr=sr, aggregate=None)
                tempos[i] = float(t.mean()) if len(t) > 0 else 0.0
            except Exception:
                tempos[i] = tempos[i - 1] if i > 0 else 0.0

        tempo_diff = np.abs(np.diff(tempos, prepend=tempos[0]))
        return self._normalize(self._resize_to(tempo_diff, n_samples))

    def _signal_spectral_flux(self, y: np.ndarray, sr: int, hop: _Hop,
                              n_samples: int) -> np.ndarray:
        """S4 — Aggregierter Spectral-Flux (librosa.onset.onset_strength)."""
        librosa, _ = self._import_deps()
        flux = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop.hop_samples)
        # Aggregiere auf Sekunden-Bloecke (~1 s Fenster)
        block = max(1, int(1.0 / self.hop_seconds))
        if len(flux) >= block:
            n_blocks = len(flux) // block
            agg = flux[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
        else:
            agg = flux
        flux_diff = np.abs(np.diff(agg, prepend=agg[0]))
        return self._normalize(self._resize_to(flux_diff, n_samples))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _effective_weights(self, stems_used: bool) -> dict[str, float]:
        if stems_used:
            return dict(self.weights)
        # Re-normalisiere ohne S2
        w = {k: v for k, v in self.weights.items() if k != "stem"}
        s = sum(w.values()) or 1.0
        renormalized = {k: v / s for k, v in w.items()}
        renormalized["stem"] = 0.0
        return renormalized

    @staticmethod
    def _normalize(x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x
        max_val = float(np.abs(x).max())
        if max_val < 1e-12:
            return np.zeros_like(x)
        return x / max_val

    @staticmethod
    def _resize_to(x: np.ndarray, n: int) -> np.ndarray:
        """Lineare Resampling auf n Samples (numpy-only, keine scipy.interp1d)."""
        if x.size == 0:
            return np.zeros(n)
        if x.size == n:
            return x
        old_idx = np.linspace(0, 1, num=x.size)
        new_idx = np.linspace(0, 1, num=n)
        return np.interp(new_idx, old_idx, x)

    def _peak_pick(self, fused: np.ndarray, hop_seconds: float,
                   duration: float) -> list[float]:
        """Adaptive-Threshold Peak-Picking mit min_distance constraint."""
        _librosa, signal = self._import_deps()
        if fused.size == 0:
            return []
        threshold = float(fused.mean() + self.adaptive_threshold_k * fused.std())
        if not np.isfinite(threshold):
            threshold = 0.5
        min_dist_samples = int(self.min_distance_seconds / hop_seconds)
        peaks, _ = signal.find_peaks(
            fused, height=threshold, distance=max(1, min_dist_samples),
        )
        # Boundaries in Sekunden, ohne 0 und Ende
        boundaries = [float(p * hop_seconds) for p in peaks
                      if 5.0 < float(p * hop_seconds) < duration - 5.0]
        return boundaries

    @staticmethod
    def _boundaries_to_segments(
        boundaries: list[float],
        duration: float,
        fused: np.ndarray,
        hop_seconds: float,
    ) -> list[SubtrackSegment]:
        """Boundaries → Segmente. Wenn 0 Boundaries: Fallback 1 Segment."""
        if not boundaries:
            return [SubtrackSegment(
                start_time=0.0, end_time=duration, confidence=0.5,
            )]
        marks = [0.0] + sorted(boundaries) + [duration]
        segments: list[SubtrackSegment] = []
        for s, e in zip(marks[:-1], marks[1:]):
            # Confidence: Mittel des fused-Signal im Segment
            mid_idx = int(((s + e) / 2.0) / hop_seconds)
            mid_idx = max(0, min(fused.size - 1, mid_idx)) if fused.size else 0
            conf = float(fused[mid_idx]) if fused.size else 0.5
            segments.append(SubtrackSegment(
                start_time=float(s), end_time=float(e),
                confidence=max(0.0, min(1.0, conf)),
            ))
        return segments
