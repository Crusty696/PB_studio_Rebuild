"""Tests fuer services.brain_v3.gpu_serializer.

CPU-only — kein torch/cuda noetig. Pruefen Lock-Semantik, async, holder-Tracking.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from services.brain_v3.gpu_serializer import (
    GpuSerializer, get_default_serializer, reset_default_serializer_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_default():
    reset_default_serializer_for_tests()
    yield
    reset_default_serializer_for_tests()


def test_acquire_releases_lock():
    s = GpuSerializer(empty_cache_on_release=False)
    assert not s.is_locked()
    with s.acquire("test"):
        assert s.is_locked()
        assert s.current_holder() == "test"
    assert not s.is_locked()
    assert s.current_holder() is None


def test_serializer_serializes_two_threads():
    """Zwei Threads ueberlappen sich NICHT in der kritischen Section."""
    s = GpuSerializer(empty_cache_on_release=False)
    in_section = []
    barrier = threading.Barrier(2)

    def worker(name: str):
        barrier.wait()
        with s.acquire(name):
            in_section.append((name, "enter"))
            time.sleep(0.05)
            in_section.append((name, "exit"))

    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Sequenz muss [enter, exit, enter, exit] sein, nicht interleaved
    events = [evt for _name, evt in in_section]
    assert events == ["enter", "exit", "enter", "exit"]


def test_holder_restored_after_nested_use():
    """Nested acquire (sollte normalerweise nicht passieren, aber holder-Restore testbar)."""
    s = GpuSerializer(empty_cache_on_release=False)
    with s.acquire("outer"):
        assert s.current_holder() == "outer"
    assert s.current_holder() is None


def test_default_singleton_returns_same_instance():
    s1 = get_default_serializer()
    s2 = get_default_serializer()
    assert s1 is s2


def test_reset_default_creates_new_instance():
    s1 = get_default_serializer()
    reset_default_serializer_for_tests()
    s2 = get_default_serializer()
    assert s1 is not s2


def test_async_acquire_serializes():
    s = GpuSerializer(empty_cache_on_release=False)
    events: list[tuple[str, str]] = []

    async def worker(name: str, delay: float):
        async with s.acquire_async(name):
            events.append((name, "enter"))
            await asyncio.sleep(delay)
            events.append((name, "exit"))

    async def run():
        await asyncio.gather(worker("A", 0.05), worker("B", 0.05))

    asyncio.run(run())
    seq = [e for _n, e in events]
    assert seq == ["enter", "exit", "enter", "exit"]


def test_empty_cache_on_release_does_not_crash_without_torch(monkeypatch):
    """empty_cache muss bei fehlendem torch oder CUDA nicht eskalieren."""
    s = GpuSerializer(empty_cache_on_release=True)
    # Auch ohne CUDA-Hardware sollte das funktionieren
    with s.acquire("test"):
        pass
    # Kein Exception erwartet


def test_serializer_waits_for_legacy_gpu_execution_lock():
    """Brain-V3-GPU-Workloads muessen mit Demucs/RAFT/BeatThis serialisieren."""
    from services.model_manager import GPU_EXECUTION_LOCK

    s = GpuSerializer(empty_cache_on_release=False)
    entered = threading.Event()
    finished = threading.Event()

    def worker():
        with s.acquire("clap_embed_mix"):
            entered.set()
        finished.set()

    GPU_EXECUTION_LOCK.acquire()
    try:
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        time.sleep(0.05)
        assert not entered.is_set()
    finally:
        GPU_EXECUTION_LOCK.release()

    assert finished.wait(timeout=2.0)
