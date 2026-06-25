"""B-584: convert_service erzwingt 8-bit pix_fmt bei 10-bit-Input fuer h264_nvenc.

Pascal (GTX 1060) kann h264_nvenc nur in 8-bit. Eine 10-bit-Quelle
(yuv420p10le / p010le / HEVC Main10) laeuft sonst in
"10 bit encode not supported". export_service erzwingt yuv420p,
convert_service tat das NICHT.

Diese Tests mocken ffmpeg/ffprobe vollstaendig — KEIN echter ffmpeg-Aufruf.
Sie fangen den zusammengebauten ffmpeg-Argument-Vektor ab und pruefen, ob
bei 10-bit-Input `-pix_fmt yuv420p` im Output erzwungen wird.
"""

from __future__ import annotations

from pathlib import Path

import services.convert_service as cs


def _run_convert_capture(monkeypatch, tmp_path: Path, probed_pix_fmt: str) -> list[str]:
    """Ruft convert() mit gemockten ffmpeg/ffprobe und liefert das cmd zurueck.

    - detect_nvenc: h264_nvenc + cuda_hwaccel verfuegbar
    - pix_fmt-Probe: liefert ``probed_pix_fmt``
    - _get_duration: 0.0 (irrelevant)
    - _run_ffmpeg_with_progress: faengt cmd ab, erstellt Output-Datei
    """
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        cs,
        "detect_nvenc",
        lambda: {
            "h264_nvenc": True,
            "hevc_nvenc": True,
            "cuda_hwaccel": True,
            "ffmpeg_version": "test",
        },
    )

    def _fake_run(cmd, total_duration, progress_cb, cancel_check=None, timeout=None):
        captured["cmd"] = list(cmd)
        # Output-Pfad ist das letzte cmd-Element — Datei anlegen, damit
        # convert() die Erfolgs-Pruefung (exists + size > 0) besteht.
        Path(cmd[-1]).write_bytes(b"\x00\x01")
        return "stderr"

    monkeypatch.setattr(cs, "_run_ffmpeg_with_progress", _fake_run)
    monkeypatch.setattr(cs, "_get_duration", lambda _p: 0.0)
    # pix_fmt-Probe mocken.
    monkeypatch.setattr(cs, "_get_pix_fmt", lambda _p: probed_pix_fmt, raising=True)

    # GpuSerializer.acquire umgehen (NVENC-Pfad nutzt ihn).
    import services.brain_v3.gpu_serializer as gs

    class _NullCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _NullSerializer:
        def acquire(self, _holder):
            return _NullCtx()

    monkeypatch.setattr(gs, "get_default_serializer", lambda: _NullSerializer())

    src = tmp_path / "input.mov"
    src.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    cs.convert(str(src), preset_name="master", output_path=str(out))
    return captured["cmd"]


def test_10bit_input_forces_yuv420p(monkeypatch, tmp_path):
    cmd = _run_convert_capture(monkeypatch, tmp_path, "yuv420p10le")
    # Erwartung: bei 10-bit-Input wird -pix_fmt yuv420p in den Output gezwungen.
    assert "-pix_fmt" in cmd, f"-pix_fmt fehlt komplett: {cmd}"
    idx = cmd.index("-pix_fmt")
    assert cmd[idx + 1] == "yuv420p", f"Falsches pix_fmt: {cmd}"


def test_8bit_input_no_forced_downconvert(monkeypatch, tmp_path):
    cmd = _run_convert_capture(monkeypatch, tmp_path, "yuv420p")
    # 8-bit-Input: kein erzwungenes Downconvert (Verhalten unveraendert).
    assert "-pix_fmt" not in cmd, f"Unerwartetes -pix_fmt bei 8-bit: {cmd}"
