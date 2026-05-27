"""B-336: ModelManager laedt fp16 mit NaN-Guard + fp32-Fallback.

Testet die reine Entscheidungslogik von ``_load_with_fp16_nan_guard`` ueber
injizierte load_fn/smoke_fn — kein echtes Modell/GPU noetig.
"""
from __future__ import annotations

import torch

from services.model_manager import ModelManager


def _mgr(device: str) -> ModelManager:
    # __init__ umgehen — nur self.device wird von der Methode gebraucht.
    m = object.__new__(ModelManager)
    m.device = device
    return m


def test_all_finite_detects_nan_inf():
    assert ModelManager._all_finite(torch.tensor([1.0, 2.0, 3.0])) is True
    assert ModelManager._all_finite(torch.tensor([1.0, float("nan")])) is False
    assert ModelManager._all_finite(torch.tensor([1.0, float("inf")])) is False


def test_guard_keeps_fp16_when_output_finite():
    m = _mgr("cuda:0")
    calls = []
    out = m._load_with_fp16_nan_guard(
        lambda dt: calls.append(dt) or f"m{dt}",
        lambda model: True,
        "X",
    )
    assert calls == [torch.float16]
    assert out == f"m{torch.float16}"


def test_guard_falls_back_to_fp32_on_nan():
    m = _mgr("cuda:0")
    calls = []
    out = m._load_with_fp16_nan_guard(
        lambda dt: calls.append(dt) or f"m{dt}",
        lambda model: False,
        "X",
    )
    assert calls == [torch.float16, torch.float32]
    assert out == f"m{torch.float32}"


def test_guard_keeps_fp16_when_smoke_raises():
    m = _mgr("cuda:0")
    calls = []

    def _smoke(model):
        raise RuntimeError("Modell braucht anderen Input")

    out = m._load_with_fp16_nan_guard(
        lambda dt: calls.append(dt) or dt, _smoke, "X")
    assert calls == [torch.float16]
    assert out == torch.float16


def test_guard_cpu_always_fp32_without_smoke():
    m = _mgr("cpu")
    calls = []
    smoked = []
    out = m._load_with_fp16_nan_guard(
        lambda dt: calls.append(dt) or dt,
        lambda model: smoked.append(1) or True,
        "X",
    )
    assert calls == [torch.float32]
    assert smoked == []
    assert out == torch.float32
