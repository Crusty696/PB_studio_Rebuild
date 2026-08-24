"""B-881: Filtergraph needs zero-based inputs and one final frame cap.

Real W7 evidence: eight individually rendered batches exceeded their slot sums
by 5,2,6,6,2,3,13,1 frames. Stream-copy concat reproduced the exact +38-frame
sum. Two causes were measured: seeked inputs retained non-zero PTS, and the
per-input ``fps`` filters independently rounded short slots up. Inputs therefore
start at PTS zero and the finished composite is capped once to the rounded slot
sum.
"""

from pathlib import Path

import services.export_service as export_service


def _segment(path: str, start: float, source_start: float) -> dict:
    return {
        "path": path,
        "start": start,
        "end": start + 3.0,
        "source_duration": 3.0,
        "duration": 10.0,
        "source_start": source_start,
        "crossfade": 1.0,
        "brightness": 0.0,
        "contrast": 1.0,
    }


def test_filtergraph_resets_pts_and_caps_composite_frames(tmp_path, monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"video")

    monkeypatch.setattr(export_service, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(
        export_service,
        "_prepare_normalized_audio",
        lambda *args, **kwargs: (None, args[3]),
    )
    segments = [
        _segment("first.mp4", 0.0, 4.125),
        _segment("second.mp4", 3.0, 1.750),
    ]

    export_service._export_with_filtergraph(
        segments,
        None,
        tmp_path / "output.mp4",
        1920,
        1080,
        30,
        None,
        4,
    )

    command = captured["command"]
    graph = command[command.index("-filter_complex") + 1]
    for index in range(len(segments)):
        assert f"[{index}:v]setpts=PTS-STARTPTS,scale=" in graph
    # Zwei 3-s-Slots bei 30 fps muessen als fertiges Composite exakt auf
    # 180 Frames begrenzt werden; per-Input fps-Ceil darf nicht kumulieren.
    assert "trim=end_frame=180,setpts=PTS-STARTPTS[vout]" in graph
    assert command[command.index("-map") + 1] == "[vout]"
