"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T1.4: PipelineContext - shared state container for Stages.

A-5: VRAM-Hygiene - keine Tensoren / grosse ndarrays im Context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Any, Callable


_LARGE_NBYTES_THRESHOLD = 1_000_000  # 1 MB


class ContextTensorRejected(ValueError):
    """A-5: gross-Tensor oder ndarray > 1 MB im Context-Result abgelehnt."""


def _is_disallowed_tensor(value: Any) -> bool:
    """A-5: pruefe ob value eine grosse Tensor/ndarray-Instanz ist."""
    # ndarray-Check
    try:
        import numpy as np
        if isinstance(value, np.ndarray) and value.nbytes > _LARGE_NBYTES_THRESHOLD:
            return True
    except ImportError:
        pass
    # torch-Check
    try:
        import torch
        if isinstance(value, torch.Tensor):
            nbytes = value.element_size() * value.nelement()
            if nbytes > _LARGE_NBYTES_THRESHOLD:
                return True
    except ImportError:
        pass
    return False


@dataclass
class PipelineContext:
    """Shared state pro Track durch alle Pipeline-Stages.

    A-5: speichert NUR Pfade, kleine Skalar-Resultate, JSON-serialisierbare Daten.
    NIE Tensoren > 1 MB, ndarrays > 1 MB, Audio-Sample-Arrays.
    """

    track_id: int
    original_path: str
    stem_paths: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    save_lock: threading.RLock = field(default_factory=threading.RLock)
    should_stop: Callable[[], bool] | None = None

    def set_result(self, stage_name: str, value: Any) -> None:
        """Setze Stage-Result. Raised bei Tensor-Guard-Verletzung (A-5)."""
        if _is_disallowed_tensor(value):
            raise ContextTensorRejected(
                f"A-5 Tensor-Guard: Stage '{stage_name}' versucht Tensor/ndarray "
                f">{_LARGE_NBYTES_THRESHOLD} bytes in Context zu schreiben"
            )
        with self.save_lock:
            self.results[stage_name] = value
