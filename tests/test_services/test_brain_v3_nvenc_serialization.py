from __future__ import annotations


def test_convert_nvenc_runs_inside_brain_v3_render_serializer(monkeypatch, tmp_path):
    """NVENC-Render muss denselben Brain-V3-Serializer wie CLAP/SigLIP nutzen."""
    from services import convert_service
    from services.brain_v3.gpu_serializer import (
        get_default_serializer,
        reset_default_serializer_for_tests,
    )

    reset_default_serializer_for_tests()
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "out.mp4"
    input_path.write_bytes(b"fake video")

    monkeypatch.setattr(
        convert_service,
        "detect_nvenc",
        lambda: {"h264_nvenc": True, "hevc_nvenc": True, "cuda_hwaccel": False},
    )
    monkeypatch.setattr(convert_service, "_get_duration", lambda _path: 1.0)

    holder_seen = []

    def fake_run(cmd, total_duration, progress_cb, cancel_check=None, timeout=None):
        holder_seen.append(get_default_serializer().current_holder())
        output_path.write_bytes(b"encoded")
        return ""

    monkeypatch.setattr(convert_service, "_run_ffmpeg_with_progress", fake_run)

    try:
        result = convert_service.convert(
            input_path,
            preset_name="edit_proxy",
            output_path=output_path,
            timeout=1.0,
        )
    finally:
        reset_default_serializer_for_tests()

    assert result == str(output_path)
    assert holder_seen == ["render"]
