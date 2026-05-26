"""B-103 / BUG-A9 regression test:

``BatchConvertWorker`` previously emitted BOTH ``error`` AND ``finished``
in the FileNotFoundError ("ffmpeg nicht gefunden") branch. UI slots wired
directly to ``finished`` (e.g. ``ui/controllers/convert.py::_on_batch_convert_finished``)
fired AFTER the error handler, overwriting the error state with a
"converted X/Y" success message.

This test verifies that the FNF branch only emits ``error``, never
``finished``.
"""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from workers.import_export import BatchConvertWorker


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_batch_convert_ffmpeg_missing_emits_error_only_no_finished(
    tmp_path,
):  # noqa: ANN001
    """When ffmpeg is missing (FileNotFoundError), the worker must emit
    ``error`` exactly once and ``finished`` NEVER. Earlier code emitted
    both, causing UI slots wired to ``finished`` to overwrite the error
    state with a fake success."""
    _ensure_qapp()

    # Construct a worker with one fake video. The actual file does not
    # need to exist — subprocess will raise FileNotFoundError when ffmpeg
    # is "missing".
    # Worker expects videos as list of dicts with "file_path" key.
    fake_video_path = tmp_path / "input.mp4"
    fake_video_path.write_bytes(b"")  # touch
    worker = BatchConvertWorker(
        [{"file_path": str(fake_video_path)}],
        resolution="1920x1080", fps="30", vcodec="libx264",
        ext=".mp4",
    )

    finished_calls: list[tuple[int, int]] = []
    error_calls: list[str] = []

    worker.finished.connect(lambda c, t: finished_calls.append((c, t)))
    worker.error.connect(lambda msg: error_calls.append(msg))

    # Mock subprocess.Popen so the inner ffmpeg invocation raises
    # FileNotFoundError, which is the BUG-A9 trigger branch.
    def raise_fnf(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("ffmpeg")

    with patch("workers.import_export.subprocess.Popen", side_effect=raise_fnf):
        worker.run()

    assert len(error_calls) == 1, (
        f"Expected exactly 1 error emission, got {len(error_calls)}: "
        f"{error_calls}"
    )
    assert "ffmpeg" in error_calls[0].lower()

    assert finished_calls == [], (
        f"BUG-A9 regression: ``finished`` was emitted on the error branch. "
        f"Got: {finished_calls}. Expected no ``finished`` emission so the "
        f"UI slot does not overwrite the error state."
    )
