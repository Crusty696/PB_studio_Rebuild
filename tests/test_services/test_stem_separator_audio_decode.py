import subprocess
from pathlib import Path

import numpy as np
import torch


class _BrokenTorchaudio:
    calls = []

    @staticmethod
    def load(path: str):
        _BrokenTorchaudio.calls.append(path)
        if path.endswith(".m4a"):
            raise RuntimeError("Format not recognised")
        stereo = torch.tensor(
            [
                [0.1, -0.2, 0.3],
                [0.4, -0.5, 0.6],
            ],
            dtype=torch.float32,
        )
        return stereo, 44100


def test_stem_separator_audio_loader_falls_back_to_ffmpeg_for_m4a(monkeypatch, tmp_path: Path):
    from services import ai_audio_service

    src = tmp_path / "track.m4a"
    src.write_bytes(b"not real m4a; ffmpeg is mocked")

    def fake_run(cmd, capture_output, timeout, check, **_kwargs):
        assert str(src) in cmd
        assert "pcm_f32le" in cmd
        assert "wav" in cmd
        assert "44100" in cmd
        output_path = Path(cmd[-1])
        output_path.write_bytes(b"fake wav")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ai_audio_service, "get_ffmpeg_bin", lambda: "ffmpeg")
    monkeypatch.setattr(ai_audio_service.subprocess, "run", fake_run)
    _BrokenTorchaudio.calls = []

    waveform, sr = ai_audio_service._load_audio_for_stem_separation(
        src,
        _BrokenTorchaudio,
        target_sr=44100,
    )

    assert sr == 44100
    assert tuple(waveform.shape) == (2, 3)
    assert np.allclose(
        waveform.numpy(),
        np.array([[0.1, -0.2, 0.3], [0.4, -0.5, 0.6]], dtype=np.float32),
    )
    assert _BrokenTorchaudio.calls[0].endswith(".m4a")
    assert _BrokenTorchaudio.calls[1].endswith(".wav")


def test_streaming_stem_writer_crossfades_without_full_accumulator(tmp_path: Path):
    import soundfile as sf
    from services.ai_audio_service import _StreamingStemWriter

    writer = _StreamingStemWriter(
        tmp_path,
        ["vocals"],
        channels=1,
        sample_rate=44100,
    )
    chunk_1 = torch.tensor([[[1.0, 2.0, 3.0, 4.0, 5.0]]])
    fade_1 = torch.tensor([1.0, 1.0, 1.0, 1.0, 0.0])
    chunk_2 = torch.tensor([[[10.0, 20.0, 30.0, 40.0, 50.0]]])
    fade_2 = torch.tensor([0.0, 1.0, 1.0, 1.0, 1.0])

    writer.write_chunk(chunk_1 * fade_1.unsqueeze(0).unsqueeze(0), fade_1, ["vocals"], 2, False)
    writer.write_chunk(chunk_2 * fade_2.unsqueeze(0).unsqueeze(0), fade_2, ["vocals"], 2, True)
    writer.close(["vocals"])

    data, sr = sf.read(writer.paths["vocals"], dtype="float32")

    assert sr == 44100
    assert np.allclose(data, np.array([1.0, 2.0, 3.0, 4.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float32))
