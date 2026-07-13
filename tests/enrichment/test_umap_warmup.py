"""B-618: Numba-JIT-Kaltstart-Warmup fuer umap/pynndescent.

Der Lazy-Import von umap (direkt in ``fit()`` bzw. indirekt via
``pickle.load`` in ``load_reducer()``) loest bei kaltem Numba-Disk-Cache
JIT-Kompilierung aus, die den GIL des App-Prozesses so lange haelt, dass
der Qt-Main-Thread eskalierend blockiert und der Prozess spurlos stirbt
(live-belegt 2026-07-13).

Diese Tests pinnen das neue Verhalten: ``warm_umap_cache()`` fuellt den
Numba-Disk-Cache in einem SEPARATEN Subprocess (haelt den GIL des
App-Prozesses nicht), ist idempotent und thread-safe, wird in Frozen-Builds
(PyInstaller) kontrolliert uebersprungen und crasht nie den Aufrufer.
"""

from __future__ import annotations

import pickle
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

import services.enrichment.style_bucket_clusterer as sbc
from services.enrichment.style_bucket_clusterer import StyleBucketClusterer


@pytest.fixture(autouse=True)
def _reset_warmup_state():
    """Jeder Test startet mit kaltem Warmup-Zustand; danach Original zurueck."""
    old = sbc._WARMUP_STATE["done"]
    sbc._WARMUP_STATE["done"] = False
    yield
    sbc._WARMUP_STATE["done"] = old


def _make_fake_run(calls: list, side_effect: Exception | None = None, delay: float = 0.0):
    def fake_run(cmd, **kwargs):
        if delay:
            time.sleep(delay)
        calls.append((cmd, kwargs))
        if side_effect is not None:
            raise side_effect
        return subprocess.CompletedProcess(cmd, 0)

    return fake_run


def test_cold_cache_runs_warmup_subprocess(monkeypatch):
    """Kalter Cache: genau ein Subprocess `python -c "import umap"`."""
    monkeypatch.delitem(sys.modules, "umap", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls))

    assert sbc.warm_umap_cache() is True
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == [sys.executable, "-c", "import umap"]
    assert kwargs.get("timeout") is not None
    assert kwargs.get("check") is True


def test_warmup_skipped_when_umap_already_imported(monkeypatch):
    """umap bereits in sys.modules -> JIT-Kosten schon bezahlt, kein Subprocess."""
    monkeypatch.setitem(sys.modules, "umap", object())
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls))

    assert sbc.warm_umap_cache() is True
    assert calls == []


def test_warmup_skipped_in_frozen_build(monkeypatch):
    """PyInstaller: sys.executable ist die App-EXE -> Warmup kontrolliert skippen."""
    monkeypatch.delitem(sys.modules, "umap", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls))

    assert sbc.warm_umap_cache() is False
    assert calls == []


def test_warmup_idempotent_second_call_no_subprocess(monkeypatch):
    monkeypatch.delitem(sys.modules, "umap", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls))

    assert sbc.warm_umap_cache() is True
    assert sbc.warm_umap_cache() is True
    assert len(calls) == 1


@pytest.mark.parametrize(
    "side_effect",
    [
        subprocess.CalledProcessError(1, ["python", "-c", "import umap"]),
        subprocess.TimeoutExpired(["python", "-c", "import umap"], 1.0),
        OSError("exe not found"),
    ],
)
def test_warmup_failure_falls_back_without_raising(monkeypatch, side_effect):
    """Subprocess-Fehler/Timeout: kein Raise, False zurueck, kein Retry-Sturm."""
    monkeypatch.delitem(sys.modules, "umap", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls, side_effect=side_effect))

    assert sbc.warm_umap_cache() is False
    assert len(calls) == 1
    # Kein zweiter Subprocess-Versuch: In-Process-Import fuellt den Cache selbst.
    assert sbc.warm_umap_cache() is True
    assert len(calls) == 1


def test_warmup_thread_safe_single_subprocess(monkeypatch):
    """8 parallele Aufrufer -> genau 1 Subprocess, alle bekommen True."""
    monkeypatch.delitem(sys.modules, "umap", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    calls: list = []
    monkeypatch.setattr(sbc.subprocess, "run", _make_fake_run(calls, delay=0.05))

    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(sbc.warm_umap_cache()))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert results == [True] * 8


def test_load_reducer_warms_cache_before_unpickle(tmp_path: Path, monkeypatch):
    """load_reducer(): Warmup MUSS vor pickle.load laufen (Unpickling importiert umap)."""
    order: list[str] = []
    monkeypatch.setattr(sbc, "warm_umap_cache", lambda: order.append("warmup"))

    payload = {"stub": 1}
    path = tmp_path / "umap_v1.pkl"
    with open(path, "wb") as f:
        pickle.dump(payload, f)

    real_load = sbc.pickle.load

    def spy_load(fobj):
        order.append("unpickle")
        return real_load(fobj)

    monkeypatch.setattr(sbc.pickle, "load", spy_load)

    loaded = StyleBucketClusterer.load_reducer(path)
    assert loaded == payload
    assert order == ["warmup", "unpickle"]


def test_load_reducer_missing_file_does_not_warm(tmp_path: Path, monkeypatch):
    """Fehlende Reducer-Datei -> FileNotFoundError wie bisher, kein Warmup."""
    order: list[str] = []
    monkeypatch.setattr(sbc, "warm_umap_cache", lambda: order.append("warmup"))

    with pytest.raises(FileNotFoundError):
        StyleBucketClusterer.load_reducer(tmp_path / "missing.pkl")
    assert order == []


def test_fit_small_library_degraded_does_not_warm(monkeypatch):
    """Degraded-Pfad (kleine Library) importiert kein umap -> kein Warmup."""
    order: list[str] = []
    monkeypatch.setattr(sbc, "warm_umap_cache", lambda: order.append("warmup"))

    clusterer = StyleBucketClusterer()
    result = clusterer.fit(np.zeros((3, 1152), dtype=np.float32))
    assert result.degraded is True
    assert order == []


def test_fit_warms_cache_and_still_clusters(monkeypatch):
    """fit() ruft Warmup vor dem umap-Import; Cluster-Ergebnis bleibt funktionsfaehig."""
    order: list[str] = []
    monkeypatch.setattr(sbc, "warm_umap_cache", lambda: order.append("warmup"))

    rng = np.random.default_rng(42)
    blob_centers = rng.normal(size=(3, 64)) * 5.0
    embeddings = np.concatenate(
        [rng.normal(c, 0.3, size=(15, 64)) for c in blob_centers]
    ).astype(np.float32)

    clusterer = StyleBucketClusterer(n_neighbors=10)
    result = clusterer.fit(embeddings)

    assert order == ["warmup"]
    assert result.degraded is False
    assert result.reducer is not None
    assert result.labels.shape == (45,)
