"""Brain V3 — VisualCurves-Extractor (Plan-Doc 06 Phase 1).

Berechnet Brightness, Saturation und Color-Temperature pro Frame.
Default: 1 Sample pro Sekunde (sample_rate_hz=1.0).

CPU-only via opencv-python (cv2). Kein GPU-Bedarf.

Designs:
- Brightness:  HSV V-Channel Mean → 0..1
- Saturation:  HSV S-Channel Mean → 0..1
- ColorTemp:   Approximation als log(R/B) — positiv = warm (Sonne),
               negativ = kalt (Schatten/Nacht). Skaliert auf -1..+1.

Nicht-Kelvin-Skala — wir wollen relative Vergleichbarkeit zwischen
Frames eines Mix, nicht Kalibrierung gegen physikalisches Modell.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from services.brain.schemas.video import (
    CurvePoint, VisualCurves, VisualCurvesResult,
)

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE_HZ = 1.0  # Plan-Doc 06: 1 Sample pro Sekunde


class VisualCurvesExtractor:
    """Streamt Frames eines Videos, berechnet 3 Visual-Kurven.

    Usage:
        ex = VisualCurvesExtractor()
        result = ex.extract(video_path, video_hash="...")
    """

    def __init__(self, sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError(f"sample_rate_hz muss > 0 sein: {sample_rate_hz}")
        self.sample_rate_hz = sample_rate_hz
        self._cv2 = None

    def _import_deps(self):
        if self._cv2 is None:
            import cv2  # type: ignore
            self._cv2 = cv2
        return self._cv2

    def extract(
        self,
        video_path: Path | str,
        video_hash: str,
        max_seconds: Optional[float] = None,
    ) -> VisualCurvesResult:
        """Frame-Sampling + Kurven-Berechnung.

        Args:
            video_path: Pfad zur Video-Datei (mp4, mov, mkv, ...).
            video_hash: sha256 der Video-Datei (von services.brain.hashing).
            max_seconds: optional Max-Dauer fuer Tests (clamp).

        Returns:
            VisualCurvesResult mit 3 Kurven a sample_rate_hz Hz.
        """
        cv2 = self._import_deps()
        cap = cv2.VideoCapture(str(video_path))
        try:
            if not cap.isOpened():
                raise IOError(f"OpenCV konnte Video nicht oeffnen: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps <= 0 or n_frames <= 0:
                raise ValueError(f"Ungueltige Video-Metadaten fuer {video_path}: "
                                 f"fps={fps}, frames={n_frames}")

            duration = float(n_frames / fps)
            if max_seconds is not None:
                duration = min(duration, max_seconds)
            if duration <= 0:
                raise ValueError(f"Video zu kurz ({duration} s): {video_path}")

            n_samples = max(1, int(duration * self.sample_rate_hz))
            sample_indices = np.linspace(
                0, min(n_frames - 1, int(duration * fps) - 1),
                num=n_samples, dtype=int,
            )

            brightness: list[CurvePoint] = []
            saturation: list[CurvePoint] = []
            color_temp: list[CurvePoint] = []

            for sample_idx, frame_idx in enumerate(sample_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
                ok, frame_bgr = cap.read()
                if not ok or frame_bgr is None:
                    logger.debug("VisualCurves: skip frame %d (read failed)", frame_idx)
                    continue
                t = float(sample_idx / self.sample_rate_hz)
                b_val, s_val, ct_val = self._compute_metrics(frame_bgr, cv2)
                brightness.append(CurvePoint(time=t, value=b_val))
                saturation.append(CurvePoint(time=t, value=s_val))
                color_temp.append(CurvePoint(time=t, value=ct_val))

            curves = VisualCurves(
                sample_rate_hz=self.sample_rate_hz,
                duration_seconds=duration,
                brightness=brightness,
                saturation=saturation,
                color_temperature=color_temp,
            )
            return VisualCurvesResult(
                video_hash=video_hash,
                duration_seconds=duration,
                sample_rate_hz=self.sample_rate_hz,
                n_samples=len(brightness),
                curves=curves,
            )
        finally:
            cap.release()

    @staticmethod
    def _compute_metrics(frame_bgr: np.ndarray, cv2_mod) -> tuple[float, float, float]:
        """Per-Frame-Berechnung: Brightness, Saturation, ColorTemp.

        Returns:
            (brightness 0..1, saturation 0..1, color_temp -1..+1)
        """
        # HSV fuer Brightness + Saturation
        hsv = cv2_mod.cvtColor(frame_bgr, cv2_mod.COLOR_BGR2HSV)
        brightness = float(hsv[..., 2].mean()) / 255.0
        saturation = float(hsv[..., 1].mean()) / 255.0

        # ColorTemp: warm-cool ratio aus R/B
        # frame ist BGR (OpenCV-Convention)
        b_mean = float(frame_bgr[..., 0].mean()) + 1.0  # +1 gegen log(0)
        r_mean = float(frame_bgr[..., 2].mean()) + 1.0
        log_ratio = float(np.log(r_mean / b_mean))
        # Skaliere auf -1..+1 via tanh
        color_temp = float(np.tanh(log_ratio))

        return brightness, saturation, color_temp
