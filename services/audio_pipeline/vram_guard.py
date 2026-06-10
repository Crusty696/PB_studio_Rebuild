"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T6.1: VRAM-Guard fuer GTX 1060 (6 GB).

assert_vram_available(min_free_mb): raised VRAMExhaustedError wenn unterhalb.
Cross-Pipeline-Awareness: loggt concurrent-Holders best-effort.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Default-Floor fuer Demucs htdemucs_ft (R-10 Chunk-Receptive-Field-Sicherheit).
STEM_CHUNK_MIN_SECONDS = 15


class VRAMExhaustedError(RuntimeError):
    """T6.1 / AC-13: VRAM unterhalb min_free_mb. Pipeline-Stop."""


def get_free_vram_mb() -> int | None:
    """Best-effort free VRAM in MB. None wenn CUDA nicht verfuegbar."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free_bytes, _total_bytes = torch.cuda.mem_get_info()
        return free_bytes // (1024 * 1024)
    except (ImportError, RuntimeError, AttributeError):
        return None


def assert_vram_available(min_free_mb: int = 4500) -> None:
    """Raised VRAMExhaustedError wenn free < min_free_mb.

    GTX 1060 6 GB: typischer Demucs-Bedarf 3.5-4.5 GB pro 30s-Chunk.
    Default min_free_mb=4500 gibt Sicherheits-Marge.

    Wenn CUDA nicht verfuegbar -> no-op (CPU-Fallback ohne VRAM-Check).
    """
    free = get_free_vram_mb()
    if free is None:
        return
    if free < min_free_mb:
        # T6.1 R-06: cross-pipeline-awareness Log
        logger.warning(
            "VRAM low: free=%dMB threshold=%dMB. "
            "Andere GPU-Holder (Video-Pipeline, Brain-V3 SigLIP) muessen freigeben.",
            free, min_free_mb,
        )
        raise VRAMExhaustedError(
            f"VRAM unzureichend: {free}MB frei, {min_free_mb}MB benoetigt. "
            "GTX 1060 Hartregel: nur cuda:0, kein anderer GPU-Backend."
        )


def compute_adaptive_chunk_seconds(default_sec: float, free_vram_mb: int | None,
                                    floor_sec: float = STEM_CHUNK_MIN_SECONDS) -> float:
    """R-10: adaptive Chunk-Halving bei VRAM-Druck, Floor bei 15s.

    Reduce chunk by half bei VRAM < 3500 MB. Aber niemals unter floor_sec.
    """
    chunk = float(default_sec)
    if free_vram_mb is not None and free_vram_mb < 3500:
        chunk = max(chunk / 2.0, floor_sec)
    if chunk < floor_sec:
        chunk = floor_sec
    return chunk
