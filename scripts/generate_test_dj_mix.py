"""Synthetic DJ-mix generator for P13 regression testing.

Creates a WAV of configurable length with a sinusoid-burst chain so that
onset detection has something to find, and with known structure-segment
boundaries. Output is deterministic given the same --seed.

Usage:
    python scripts/generate_test_dj_mix.py --duration-hours 3 --output out.wav
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

DEFAULT_SR: int = 22050


@dataclass(frozen=True)
class SyntheticMixSpec:
    duration_sec: float
    sr: int
    burst_interval_sec: float
    burst_freq_hz: float
    burst_duration_sec: float
    seed: int
    segment_minutes: float  # Structure segment length in minutes


def generate_mix_audio(
    spec: SyntheticMixSpec,
) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Generate the audio signal AND return the structure segments.

    Signal: silence + 50ms 440Hz bursts at `burst_interval_sec` spacing.
    Segments: (start_sec, end_sec) pairs at `segment_minutes * 60` grid.

    Returns (audio_array, segments).
    """
    total_samples = int(spec.duration_sec * spec.sr)
    audio = np.zeros(total_samples, dtype=np.float32)

    burst_samples = int(spec.burst_duration_sec * spec.sr)
    t = np.arange(burst_samples) / spec.sr
    burst = np.sin(2 * np.pi * spec.burst_freq_hz * t).astype(np.float32) * 0.4

    # Envelope: quick attack, decay — makes it look like a real onset
    envelope = np.hanning(burst_samples).astype(np.float32)
    burst = burst * envelope

    # Place bursts
    n_bursts = int(spec.duration_sec / spec.burst_interval_sec)
    for i in range(n_bursts):
        start = int(i * spec.burst_interval_sec * spec.sr)
        end = min(start + burst_samples, total_samples)
        audio[start:end] = burst[: end - start]

    # Build segment list (simple fixed-length grid)
    seg_len = spec.segment_minutes * 60.0
    segments: list[tuple[float, float]] = []
    t0 = 0.0
    while t0 + seg_len <= spec.duration_sec:
        segments.append((t0, t0 + seg_len))
        t0 += seg_len
    if t0 < spec.duration_sec:
        segments.append((t0, spec.duration_sec))

    return audio, segments


def main() -> int:
    # Force UTF-8 stdout on Windows (matches build_test_fixture.py convention)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Generate a synthetic DJ-mix audio for tests"
    )
    ap.add_argument("--duration-hours", type=float, default=3.0)
    ap.add_argument("--sr", type=int, default=DEFAULT_SR)
    ap.add_argument(
        "--burst-interval-sec",
        type=float,
        default=0.5,
        help="One burst every N seconds (default: 0.5s → 120 bpm)",
    )
    ap.add_argument("--burst-freq-hz", type=float, default=440.0)
    ap.add_argument("--burst-duration-sec", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--segment-minutes",
        type=float,
        default=30.0,
        help="Structure segment length in minutes (default: 30)",
    )
    ap.add_argument("--output", type=Path, required=True, help="Output WAV path")
    args = ap.parse_args()

    spec = SyntheticMixSpec(
        duration_sec=args.duration_hours * 3600.0,
        sr=args.sr,
        burst_interval_sec=args.burst_interval_sec,
        burst_freq_hz=args.burst_freq_hz,
        burst_duration_sec=args.burst_duration_sec,
        seed=args.seed,
        segment_minutes=args.segment_minutes,
    )
    audio, segments = generate_mix_audio(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(args.output), audio, spec.sr)
    print(
        f"wrote {args.output}  "
        f"({audio.shape[0] / spec.sr / 60:.1f} min, {len(segments)} segments)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
