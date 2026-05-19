"""GPU-Lock-Awareness (read-only VRAM-Probe).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 18 (Tier 2 Building-Blocks)

Read-only Probe ueber ``torch.cuda.mem_get_info``. Respektiert
existierenden ``GPU_EXECUTION_LOCK`` von Audio-V2 ohne ihn anzufassen —
wenn V2 GPU haelt, sieht der Probe wenig freien VRAM und wartet.
"""
from __future__ import annotations

import time


__all__ = ["current_vram_free_gb", "has_vram_budget", "wait_for_vram"]


def _cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def current_vram_free_gb(device: int = 0) -> float:
    """Liefert freien VRAM auf GPU ``device`` in GB. 0.0 falls keine CUDA."""
    if not _cuda_available():
        return 0.0
    try:
        import torch
        free_bytes, _total = torch.cuda.mem_get_info(device)
        return free_bytes / 1e9
    except Exception:
        return 0.0


def has_vram_budget(required_gb: float, *, safety_gb: float = 0.5, device: int = 0) -> bool:
    """True wenn aktuell ``required_gb + safety_gb`` frei sind."""
    free = current_vram_free_gb(device)
    return free >= (required_gb + safety_gb)


def wait_for_vram(
    required_gb: float,
    *,
    safety_gb: float = 0.5,
    timeout_s: float = 60.0,
    poll_s: float = 2.0,
    device: int = 0,
) -> bool:
    """Wartet bis ``required_gb`` frei, max ``timeout_s``.

    Returns: True wenn frei geworden, False bei Timeout.
    """
    end = time.monotonic() + timeout_s
    while True:
        if has_vram_budget(required_gb, safety_gb=safety_gb, device=device):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(poll_s)
