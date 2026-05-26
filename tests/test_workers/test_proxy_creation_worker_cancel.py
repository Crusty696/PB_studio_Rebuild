import pytest

from workers.import_export import ProxyCreationWorker


def _capture_terminal_signals(worker: ProxyCreationWorker) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    finished: list[tuple[int, str]] = []
    errors: list[tuple[int, str]] = []
    worker.finished.connect(lambda clip_id, proxy_path: finished.append((clip_id, proxy_path)))
    worker.error.connect(lambda clip_id, error_msg: errors.append((clip_id, error_msg)))
    return finished, errors


def test_b362_proxy_worker_pre_start_cancel_emits_terminal_signal(qapp):
    worker = ProxyCreationWorker(clip_id=362, video_path="missing.mp4")
    finished, errors = _capture_terminal_signals(worker)
    worker.cancel()

    def _unexpected_slot():
        pytest.fail("_run_with_slot must not run after pre-start cancel")

    worker._run_with_slot = _unexpected_slot  # type: ignore[method-assign]

    worker.run()

    assert finished == [(362, "")]
    assert errors == []


def test_b362_proxy_worker_post_acquire_cancel_emits_terminal_signal(qapp):
    worker = ProxyCreationWorker(clip_id=363, video_path="missing.mp4")
    finished, errors = _capture_terminal_signals(worker)
    calls = {"should_stop": 0}

    def _cancel_after_acquire() -> bool:
        calls["should_stop"] += 1
        return calls["should_stop"] >= 2

    worker.should_stop = _cancel_after_acquire  # type: ignore[method-assign]

    def _unexpected_slot():
        pytest.fail("_run_with_slot must not run after post-acquire cancel")

    worker._run_with_slot = _unexpected_slot  # type: ignore[method-assign]

    worker.run()

    assert calls["should_stop"] == 2
    assert finished == [(363, "")]
    assert errors == []
