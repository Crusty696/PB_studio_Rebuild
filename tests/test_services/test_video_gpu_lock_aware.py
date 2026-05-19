"""Phase 18 — GPU-Lock-Awareness RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 18 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import pytest


def test_current_vram_free_gb_returns_float():
    from services.video_pipeline.primitives.gpu_lock_aware import current_vram_free_gb
    free = current_vram_free_gb()
    assert isinstance(free, float)
    assert free >= 0.0


def test_has_budget_true_when_plenty():
    from services.video_pipeline.primitives.gpu_lock_aware import has_vram_budget
    # Sehr kleines required -> sollte immer wahr sein
    assert has_vram_budget(required_gb=0.01) is True


def test_has_budget_false_when_too_much():
    from services.video_pipeline.primitives.gpu_lock_aware import has_vram_budget
    # 1000 GB required -> immer false
    assert has_vram_budget(required_gb=1000.0) is False


def test_wait_for_vram_returns_immediately_when_free(monkeypatch):
    """Wenn VRAM sofort verfuegbar -> return True ohne Wait."""
    from services.video_pipeline.primitives.gpu_lock_aware import wait_for_vram
    ok = wait_for_vram(required_gb=0.01, timeout_s=2.0, poll_s=0.5)
    assert ok is True


def test_wait_for_vram_timeout_when_never_free(monkeypatch):
    """Wenn VRAM nie reicht -> False nach Timeout."""
    from services.video_pipeline.primitives.gpu_lock_aware import wait_for_vram
    ok = wait_for_vram(required_gb=1000.0, timeout_s=1.0, poll_s=0.3)
    assert ok is False


def test_cpu_only_fallback_when_no_cuda(monkeypatch):
    """Wenn keine CUDA verfuegbar -> current_vram_free_gb soll 0.0 zurueckgeben
    statt zu crashen."""
    import services.video_pipeline.primitives.gpu_lock_aware as mod
    monkeypatch.setattr(mod, "_cuda_available", lambda: False)
    assert mod.current_vram_free_gb() == 0.0
