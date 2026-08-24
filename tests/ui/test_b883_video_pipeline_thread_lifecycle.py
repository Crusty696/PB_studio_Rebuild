"""B-883: stale VideoPreview cleanup must not delete a newer frame job."""

from __future__ import annotations


class _DeleteProbe:
    def __init__(self) -> None:
        self.delete_calls = 0

    def deleteLater(self) -> None:
        self.delete_calls += 1


def test_stale_frame_job_cleanup_keeps_new_running_job(qapp) -> None:
    from ui.widgets.video_preview import VideoPreviewWidget

    preview = VideoPreviewWidget()
    old_thread = _DeleteProbe()
    old_worker = _DeleteProbe()
    new_thread = _DeleteProbe()
    new_worker = _DeleteProbe()
    preview._frame_thread = new_thread
    preview._frame_worker = new_worker

    preview._cleanup_frame_job(old_thread, old_worker)

    assert old_thread.delete_calls == 1
    assert old_worker.delete_calls == 1
    assert preview._frame_thread is new_thread
    assert preview._frame_worker is new_worker
    assert new_thread.delete_calls == 0
    assert new_worker.delete_calls == 0
