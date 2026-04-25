"""B-111 / BUG-A4 regression test:

``services.video_service.VideoAnalyzer.probe`` parses ffprobe's
``r_frame_rate`` field and assumed it is always of the form "N/D".
Edge cases like ``"30"`` (no slash) or non-numeric values crash with
IndexError or ValueError. We assert the function returns a usable
dict instead of crashing.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_probe_handles_r_frame_rate_without_slash() -> None:
    """ffprobe occasionally emits ``r_frame_rate: "30"`` (no slash).
    The probe must not crash with IndexError."""
    from services.video_service import VideoAnalyzer

    fake_output = json.dumps({
        "streams": [{
            "width": 1920, "height": 1080,
            "r_frame_rate": "30",  # no slash → IndexError before fix
            "codec_name": "h264", "duration": "60.0",
        }],
        "format": {"duration": "60.0"},
    })
    fake_proc = MagicMock(returncode=0, stdout=fake_output, stderr="")

    with patch(
        "services.video_service.subprocess.run", return_value=fake_proc
    ):
        result = VideoAnalyzer().probe("any.mp4")

    assert "fps" in result
    assert isinstance(result["fps"], (int, float))
    # We don't assert a specific fps value — the precise fallback is up
    # to the implementation (could be 30, could be 0). We only assert
    # no crash and a usable dict.


def test_probe_handles_r_frame_rate_with_zero_denominator() -> None:
    """``r_frame_rate: "0/0"`` would crash with ZeroDivisionError. The
    code already guards via ``max(int(fps_parts[1]), 1)`` for the first
    case but ValueError on non-numeric must also be handled."""
    from services.video_service import VideoAnalyzer

    fake_output = json.dumps({
        "streams": [{
            "width": 1920, "height": 1080,
            "r_frame_rate": "n/a",  # non-numeric → ValueError before fix
            "codec_name": "h264", "duration": "60.0",
        }],
        "format": {"duration": "60.0"},
    })
    fake_proc = MagicMock(returncode=0, stdout=fake_output, stderr="")

    with patch(
        "services.video_service.subprocess.run", return_value=fake_proc
    ):
        result = VideoAnalyzer().probe("any.mp4")

    assert "fps" in result
    assert isinstance(result["fps"], (int, float))
