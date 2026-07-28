"""B-725: CPU-/Copy-Codecs dürfen GPU-Execution-Lock nicht halten."""

from __future__ import annotations

import threading


def _contender_can_acquire(lock) -> bool:
    result: list[bool] = []

    def _contend() -> None:
        acquired = lock.acquire(blocking=False)
        result.append(acquired)
        if acquired:
            lock.release()

    thread = threading.Thread(target=_contend)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    return result == [True]


def test_cpu_and_copy_codecs_do_not_hold_gpu_execution_lock(monkeypatch) -> None:
    import services.model_manager as model_manager
    from workers.import_export import BatchConvertWorker

    lock = threading.Lock()
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", lock)

    for codec in ("copy", "libx264", "libx265", "libvpx", "libvpx-vp9", "prores_ks"):
        worker = BatchConvertWorker([], "1920x1080", "30", codec, ".mp4")
        worker._run_locked = lambda: _contender_can_acquire(lock)
        assert worker.run() is True


def test_nvenc_codec_keeps_gpu_execution_lock(monkeypatch) -> None:
    import services.model_manager as model_manager
    from workers.import_export import BatchConvertWorker

    lock = threading.Lock()
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", lock)

    worker = BatchConvertWorker([], "1920x1080", "30", "h264_nvenc", ".mp4")
    worker._run_locked = lambda: _contender_can_acquire(lock)

    assert worker.run() is False
