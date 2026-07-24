"""B-692: Finaler CUDA-Cleanup beim App-Close darf NICHT laufen, solange der
EmbeddingScheduler nicht sauber gestoppt ist (ein Embed-Job koennte noch
Tensoren auf der GPU halten -> empty_cache am GpuSerializer vorbei zerreisst den
CUDA-Context -> nativer Heap-Crash 0xC0000409).

Testet die Entscheidungslogik von ``PBWindow._final_cuda_cleanup`` isoliert.
"""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _make_fake_torch(calls):
    return types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            synchronize=lambda: calls.append("sync"),
            empty_cache=lambda: calls.append("empty"),
        )
    )


def test_cleanup_skipped_when_scheduler_not_stopped(monkeypatch):
    import main as main_mod

    calls: list[str] = []
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(calls))

    win = main_mod.PBWindow.__new__(main_mod.PBWindow)  # ohne __init__
    win._final_cuda_cleanup(scheduler_stopped=False)

    assert calls == [], "empty_cache/synchronize darf bei laufendem Embedder NICHT laufen"


def test_cleanup_runs_when_scheduler_stopped(monkeypatch):
    import main as main_mod

    calls: list[str] = []
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(calls))

    win = main_mod.PBWindow.__new__(main_mod.PBWindow)
    win._final_cuda_cleanup(scheduler_stopped=True)

    assert calls == ["sync", "empty"], "bei sauberem Stop MUSS synchronize+empty_cache laufen"
