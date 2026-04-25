"""B-068 + B-069: GPU_EXECUTION_LOCK Pattern für SigLIP-Inferenz.

- B-068: generate_embeddings() Inferenz muss unter GPU_EXECUTION_LOCK laufen.
- B-069: text_to_embedding() / texts_to_embeddings_batch() müssen
  GPU_EXECUTION_LOCK halten und GPU_LOAD_LOCK nur über `load_siglip()`.

Statt echter GPU-Inferenz monkeypatchen wir mm.load_siglip + die Stub-Methoden
get_image_features / get_text_features. Diese prüfen direkt, welcher Lock
während ihres Aufrufs gehalten ist.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _is_locked(rlock) -> bool:
    """RLock ist 'gehalten' wenn ein anderes Thread ihn nicht acquiren kann.

    RLock erlaubt re-entrant von eigenem Thread, deshalb prüfen wir via
    nicht-blockierendem acquire aus einem zweiten Thread.
    """
    import threading

    result = {"acquired": False}

    def _try():
        if rlock.acquire(blocking=False):
            rlock.release()
            result["acquired"] = True

    t = threading.Thread(target=_try)
    t.start()
    t.join()
    return not result["acquired"]


@pytest.fixture
def stub_siglip(monkeypatch):
    """Patcht mm.load_siglip + liefert Lock-Tracking bei Inferenz."""
    import torch

    from services import video_analysis_service as vas
    from services.model_manager import GPU_EXECUTION_LOCK, GPU_LOAD_LOCK

    state = {
        "exec_held_during_inference": None,
        "load_held_during_inference": None,
        "calls": 0,
    }

    class _StubProcessor:
        def __call__(self, **kwargs):
            t = torch.zeros((max(1, len(kwargs.get("text", [])) or len(kwargs.get("images", []) or [1])), 4))
            return {"input_ids": t.long()}

    def _record(out_shape):
        def _fn(**inputs):
            state["calls"] += 1
            state["exec_held_during_inference"] = _is_locked(GPU_EXECUTION_LOCK)
            state["load_held_during_inference"] = _is_locked(GPU_LOAD_LOCK)
            class _Out:
                pooler_output = torch.ones(out_shape)
            return _Out()
        return _fn

    class _StubModel:
        def __init__(self, n=1):
            self.dtype = torch.float32
            self._n = n
        def parameters(self):
            yield torch.zeros(1)
        def get_image_features(self, **inputs):
            return _record((self._n, 1152))(**inputs)
        def get_text_features(self, **inputs):
            return _record((self._n, 1152))(**inputs)

    class _StubMM:
        device = "cpu"
        def load_siglip(self):
            return _StubModel(8), _StubProcessor()
        def unload(self):
            pass

    def _factory():
        return _StubMM()

    import services.model_manager as mm_mod
    monkeypatch.setattr(mm_mod, "ModelManager", _factory)
    return state


def test_text_to_embedding_holds_execution_lock(stub_siglip, monkeypatch):
    """B-069: Inferenz darf NUR unter EXECUTION_LOCK laufen, NICHT mehr unter LOAD_LOCK."""
    from services import video_analysis_service as vas

    result = vas.text_to_embedding("a person dancing")
    assert stub_siglip["calls"] == 1
    assert stub_siglip["exec_held_during_inference"] is True, (
        "B-069: GPU_EXECUTION_LOCK muss während der Inferenz gehalten werden"
    )
    assert stub_siglip["load_held_during_inference"] is False, (
        "B-069: GPU_LOAD_LOCK darf während Inferenz NICHT mehr gehalten sein"
    )
    assert result is not None


def test_texts_to_embeddings_batch_holds_execution_lock(stub_siglip):
    """B-069: Batch-Variante gleich wie Single."""
    from services import video_analysis_service as vas

    results = vas.texts_to_embeddings_batch(["a", "b", "c"])
    assert stub_siglip["exec_held_during_inference"] is True
    assert stub_siglip["load_held_during_inference"] is False
    assert isinstance(results, dict)
