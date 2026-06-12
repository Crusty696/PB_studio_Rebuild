"""Tests fuer B-502 (RAFT-Load unter GPU_LOAD_LOCK) + B-503 (GpuSerializer
Timeout/Holder-Logging + nicht-blockierender Async-Acquire).

CPU-only — torch/torchvision werden gemockt bzw. nur monkeypatched.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import types

import pytest

from services.brain_v3.gpu_serializer import GpuSerializer


# ===== B-503: sync acquire Timeout + Holder-Info =============================

def test_sync_acquire_timeout_raises_with_holder_info():
    """Zweiter Thread haelt den Lock — kleines Timeout muss TimeoutError mit
    Holder-Info werfen statt ewig zu blockieren."""
    s = GpuSerializer(empty_cache_on_release=False)
    holding = threading.Event()
    release = threading.Event()

    def hog():
        with s.acquire("hog"):
            holding.set()
            release.wait(5.0)

    t = threading.Thread(target=hog, daemon=True)
    t.start()
    assert holding.wait(2.0)

    try:
        with pytest.raises(TimeoutError) as ei:
            with s.acquire("victim", timeout=0.3):
                pass
        msg = str(ei.value)
        assert "hog" in msg, f"Holder-Info fehlt in TimeoutError: {msg}"
        assert "victim" in msg
    finally:
        release.set()
        t.join(2.0)
    assert not s.is_locked()


def test_nested_sync_acquire_times_out_instead_of_self_deadlock():
    """Verschachteltes acquire im selben Thread (non-reentranter Lock) war
    vorher ein stiller Self-Deadlock — jetzt TimeoutError."""
    s = GpuSerializer(empty_cache_on_release=False)
    with s.acquire("outer"):
        with pytest.raises(TimeoutError) as ei:
            with s.acquire("inner", timeout=0.2):
                pass
        assert "outer" in str(ei.value)
    assert not s.is_locked()
    assert s.current_holder() is None


def test_acquire_timeout_none_blocks_until_released():
    """timeout=None = altes Verhalten (unendlich warten)."""
    s = GpuSerializer(empty_cache_on_release=False)
    holding = threading.Event()
    release = threading.Event()
    acquired = threading.Event()

    def hog():
        with s.acquire("hog"):
            holding.set()
            release.wait(5.0)

    def waiter():
        with s.acquire("waiter", timeout=None):
            acquired.set()

    t1 = threading.Thread(target=hog, daemon=True)
    t1.start()
    assert holding.wait(2.0)
    t2 = threading.Thread(target=waiter, daemon=True)
    t2.start()
    time.sleep(0.1)
    assert not acquired.is_set()
    release.set()
    assert acquired.wait(2.0)
    t1.join(2.0)
    t2.join(2.0)


# ===== B-503: async acquire blockiert den Event-Loop nicht ===================

def test_async_acquire_does_not_block_event_loop():
    """Waehrend acquire_async auf einen fremden Holder wartet, muss ein
    paralleler asyncio-Task Fortschritt machen (vorher: sync acquire in
    __aenter__ blockierte den ganzen Loop)."""
    s = GpuSerializer(empty_cache_on_release=False)
    holding = threading.Event()
    release = threading.Event()

    def hog():
        with s.acquire("hog"):
            holding.set()
            release.wait(5.0)

    t = threading.Thread(target=hog, daemon=True)
    t.start()
    assert holding.wait(2.0)

    progress: list[int] = []
    ticks_at_acquire: list[int] = []

    async def ticker():
        for i in range(10):
            progress.append(i)
            await asyncio.sleep(0.01)

    async def acquirer():
        loop = asyncio.get_running_loop()
        # Lock-Freigabe erst NACH den Ticker-Laeufen einplanen
        loop.call_later(0.25, release.set)
        async with s.acquire_async("async_consumer"):
            ticks_at_acquire.append(len(progress))

    async def run():
        await asyncio.gather(ticker(), acquirer())

    asyncio.run(run())
    t.join(2.0)

    # Loop muss waehrend der Wartezeit Fortschritt gemacht haben
    assert ticks_at_acquire, "acquire_async hat nie acquired"
    assert ticks_at_acquire[0] >= 5, (
        f"Event-Loop war blockiert: nur {ticks_at_acquire[0]} Ticks vor Acquire"
    )
    assert not s.is_locked()


def test_async_acquire_releases_legacy_lock():
    """Nach acquire_async/__aexit__ muss der legacy GPU_EXECUTION_LOCK wieder
    frei sein (RLock thread-affin → Release muss im Acquire-Thread laufen)."""
    from services.model_manager import GPU_EXECUTION_LOCK

    s = GpuSerializer(empty_cache_on_release=False)

    async def run():
        async with s.acquire_async("async_one"):
            pass

    asyncio.run(run())
    # Wenn der Release im falschen Thread lief, waere hier RuntimeError geflogen
    # bzw. der Lock dauerhaft belegt. acquire(blocking=False) prueft Freiheit.
    got = GPU_EXECUTION_LOCK.acquire(blocking=False)
    assert got, "legacy GPU_EXECUTION_LOCK wurde nach acquire_async nicht freigegeben"
    GPU_EXECUTION_LOCK.release()


# ===== B-502: RaftMotionService.load unter GPU_LOAD_LOCK + OOM-Precheck ======

class _SpyLock:
    """Context-Manager-Spy fuer GPU_LOAD_LOCK."""

    def __init__(self, events: list[str]):
        self.events = events

    def __enter__(self):
        self.events.append("load_lock:enter")
        return self

    def __exit__(self, *a):
        self.events.append("load_lock:exit")
        return False


class _FakeRaftModel:
    def __init__(self, events: list[str]):
        self._events = events

    def to(self, device):
        self._events.append(f"model:to:{device}")
        return self

    def float(self):
        return self

    def eval(self):
        self._events.append("model:eval")
        return self


def _install_fake_optical_flow(monkeypatch, events: list[str]):
    fake = types.ModuleType("torchvision.models.optical_flow")

    def raft_large(weights=None):
        events.append("raft_large:construct")
        return _FakeRaftModel(events)

    def raft_small(weights=None):
        events.append("raft_small:construct")
        return _FakeRaftModel(events)

    fake.raft_large = raft_large
    fake.raft_small = raft_small
    fake.Raft_Large_Weights = types.SimpleNamespace(C_T_SKHT_V2="w")
    fake.Raft_Small_Weights = types.SimpleNamespace(C_T_V2="w")
    # Parent-Pakete muessen importierbar sein (torchvision ist installiert);
    # sys.modules-Eintrag gewinnt bei `from torchvision.models.optical_flow import ...`.
    monkeypatch.setitem(sys.modules, "torchvision.models.optical_flow", fake)


def test_raft_load_enters_gpu_load_lock_and_runs_oom_precheck(monkeypatch):
    """B-502: raft_large-Load muss unter GPU_LOAD_LOCK laufen und vorher den
    ModelManager-OOM-Precheck (_handle_oom_prevention) ausfuehren."""
    import services.model_manager as mm_mod
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    events: list[str] = []
    _install_fake_optical_flow(monkeypatch, events)
    monkeypatch.setattr(mm_mod, "GPU_LOAD_LOCK", _SpyLock(events), raising=True)

    class _FakeMM:
        def __init__(self, *a, **kw):
            pass

        def _handle_oom_prevention(self, operation: str = "model load") -> None:
            events.append(f"oom_precheck:{operation}")

    monkeypatch.setattr(mm_mod, "ModelManager", _FakeMM, raising=True)

    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

    svc = RaftMotionService(variant="raft_large", device="cuda:0")
    svc.load()

    assert svc.is_loaded
    # Reihenfolge: Lock VOR Precheck VOR Modell-Konstruktion, Exit am Ende
    assert events[0] == "load_lock:enter"
    oom_idx = next(i for i, e in enumerate(events) if e.startswith("oom_precheck:"))
    construct_idx = events.index("raft_large:construct")
    assert oom_idx < construct_idx, "OOM-Precheck muss VOR der VRAM-Alloc laufen"
    assert "model:to:cuda:0" in events
    assert events[-1] == "load_lock:exit"
    assert any("raft_large" in e for e in events if e.startswith("oom_precheck:"))


def test_raft_load_cpu_path_skips_oom_precheck_but_holds_lock(monkeypatch):
    """Ohne CUDA: kein VRAM-Precheck noetig, aber Load weiterhin unter Lock."""
    import services.model_manager as mm_mod
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    events: list[str] = []
    _install_fake_optical_flow(monkeypatch, events)
    monkeypatch.setattr(mm_mod, "GPU_LOAD_LOCK", _SpyLock(events), raising=True)

    class _FakeMM:
        def __init__(self, *a, **kw):
            pass

        def _handle_oom_prevention(self, operation: str = "model load") -> None:
            events.append(f"oom_precheck:{operation}")

    monkeypatch.setattr(mm_mod, "ModelManager", _FakeMM, raising=True)

    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    svc = RaftMotionService(variant="raft_large", device="cuda:0")
    svc.load()

    assert svc.is_loaded
    assert "load_lock:enter" in events
    assert not any(e.startswith("oom_precheck:") for e in events)
    # Kein .to(cuda) auf CPU-Pfad
    assert not any(e.startswith("model:to:") for e in events)


def test_raft_load_is_idempotent_no_second_lock_entry(monkeypatch):
    """Zweiter load() ist Cache-Hit — kein erneuter Lock-Eintritt."""
    import services.model_manager as mm_mod
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    events: list[str] = []
    _install_fake_optical_flow(monkeypatch, events)
    monkeypatch.setattr(mm_mod, "GPU_LOAD_LOCK", _SpyLock(events), raising=True)

    class _FakeMM:
        def __init__(self, *a, **kw):
            pass

        def _handle_oom_prevention(self, operation: str = "model load") -> None:
            events.append(f"oom_precheck:{operation}")

    monkeypatch.setattr(mm_mod, "ModelManager", _FakeMM, raising=True)

    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    svc = RaftMotionService(variant="raft_small", device="cuda:0")
    svc.load()
    n_enters = events.count("load_lock:enter")
    svc.load()
    assert events.count("load_lock:enter") == n_enters
