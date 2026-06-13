import subprocess
from pathlib import Path

import numpy as np
import torch
import pytest


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
    chunk_1 = torch.tensor([[[1.0, 2.0, 3.0, 4.0, 5.0]]], dtype=torch.float16)
    fade_1 = torch.tensor([1.0, 1.0, 1.0, 1.0, 0.0], dtype=torch.float16)
    chunk_2 = torch.tensor([[[10.0, 20.0, 30.0, 40.0, 50.0]]], dtype=torch.float16)
    fade_2 = torch.tensor([0.0, 1.0, 1.0, 1.0, 1.0], dtype=torch.float16)

    writer.write_chunk(chunk_1 * fade_1.unsqueeze(0).unsqueeze(0), fade_1, ["vocals"], 2, False)
    writer.write_chunk(chunk_2 * fade_2.unsqueeze(0).unsqueeze(0), fade_2, ["vocals"], 2, True)
    writer.close(["vocals"])

    data, sr = sf.read(writer.paths["vocals"], dtype="float32")

    assert sr == 44100
    assert np.allclose(data, np.array([1.0, 2.0, 3.0, 4.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float32))


# ---------------------------------------------------------------------------
# B-510: Chunked Demucs-Input-Load — numerische Aequivalenz neu vs. alt
# ---------------------------------------------------------------------------

def _legacy_load_resample_stereo(path: Path, target_sr: int):
    """Alter Pfad vor B-510: torchaudio Full-Load + Full-Resample + Mono->Stereo."""
    import torchaudio
    waveform, sr = torchaudio.load(str(path))
    if sr != target_sr:
        waveform = torchaudio.functional.resample(waveform, sr, target_sr)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    return waveform


@pytest.mark.parametrize(
    "file_sr,channels",
    [
        (44100, 2),  # gleiche SR, stereo — reine Chunk-Kopie
        (44100, 1),  # gleiche SR, mono — Broadcast auf 2 Kanaele
        (32000, 2),  # abweichende SR — Resample pro Chunk (poly=320)
        (48000, 1),  # abweichende SR + mono (poly=160)
    ],
)
def test_chunked_loader_matches_legacy_full_load(monkeypatch, tmp_path: Path, file_sr: int, channels: int):
    """B-510: chunk-weises Laden+Resamplen muss dem alten Full-Load entsprechen.

    Toleranz-Begruendung: Chunk-Starts liegen auf dem Polyphasen-Raster des
    torchaudio-Sinc-Resamplers (identische Filterphasen) und der 1-s-Kontextrand
    deckt die Filterbreite (~ms) weit ab. Gleiche SR => bitidentische Kopie
    (atol=0). Resample-Pfad: einzige Restquelle sind conv1d-Algorithmus-
    Unterschiede bei anderer Eingangslaenge => atol 1e-6 (float32-Rauschen).
    """
    torchaudio = pytest.importorskip("torchaudio")
    import soundfile as sf_mod
    from services import ai_audio_service

    target_sr = 44100
    duration = 7.0
    rng = np.random.default_rng(42)
    n = int(duration * file_sr)
    t = np.arange(n) / file_sr
    left = 0.4 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)
    if channels == 2:
        right = 0.3 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rng.standard_normal(n)
        data = np.stack([left, right], axis=1)
    else:
        data = left[:, None]
    wav = tmp_path / f"in_{file_sr}_{channels}ch.wav"
    sf_mod.write(str(wav), data.astype(np.float32), file_sr)

    # 2-s-Chunks erzwingen, damit mehrere Chunk-Grenzen im 7-s-Signal liegen
    monkeypatch.setattr(ai_audio_service, "STEM_LOAD_CHUNK_SECONDS", 2)

    new_wf, sr = ai_audio_service._load_audio_for_stem_separation(
        wav, torchaudio, target_sr=target_sr,
    )
    legacy = _legacy_load_resample_stereo(wav, target_sr)

    assert sr == target_sr
    assert new_wf.dtype == torch.float32
    assert tuple(new_wf.shape) == tuple(legacy.shape)
    max_diff = float((new_wf - legacy).abs().max())
    if file_sr == target_sr:
        assert max_diff == 0.0, f"Gleiche SR muss bitidentisch sein, diff={max_diff:.3e}"
    else:
        assert max_diff < 1e-6, f"Resample-Aequivalenz verletzt: max diff {max_diff:.3e}"


def test_chunked_loader_rejects_empty_file(tmp_path: Path):
    """B-510: leere Datei -> RuntimeError (kein Endlos-Loop, kein 0-Array)."""
    import soundfile as sf_mod
    from services import ai_audio_service

    wav = tmp_path / "empty.wav"
    sf_mod.write(str(wav), np.zeros((0, 2), dtype=np.float32), 44100)
    with pytest.raises(RuntimeError, match="leer"):
        ai_audio_service._chunked_soundfile_load(wav, 44100, None)


def test_chunked_loader_aborts_on_should_stop(monkeypatch, tmp_path: Path):
    """B-524: should_stop unterbricht den Lade-Loop zeitnah (raise User-Cancel),
    statt einen langen Mix nach Cancel weiter zu laden und den GPU-Lock zu halten.
    """
    import soundfile as sf_mod
    from services import ai_audio_service

    file_sr = 44100
    duration = 10.0  # mit 2-s-Chunks => 5 Lade-Chunks
    n = int(duration * file_sr)
    data = (0.2 * np.sin(2 * np.pi * 220.0 * np.arange(n) / file_sr)).astype(np.float32)
    wav = tmp_path / "long.wav"
    sf_mod.write(str(wav), data, file_sr)

    monkeypatch.setattr(ai_audio_service, "STEM_LOAD_CHUNK_SECONDS", 2)

    calls = {"n": 0}

    def should_stop():
        # erster Chunk laeuft, danach Cancel
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(RuntimeError, match="abgebrochen"):
        ai_audio_service._chunked_soundfile_load(wav, 44100, None, should_stop)
    # Loop wurde frueh abgebrochen, nicht alle 5 Chunks verarbeitet.
    assert calls["n"] <= 3


def test_load_audio_propagates_cancel_without_fallback(monkeypatch, tmp_path: Path):
    """B-524: ein User-Cancel im primaeren Loader darf NICHT in den
    torchaudio-/FFmpeg-Fallback laufen, sondern muss durchpropagieren."""
    torchaudio = pytest.importorskip("torchaudio")
    import soundfile as sf_mod
    from services import ai_audio_service

    file_sr = 44100
    n = int(6.0 * file_sr)
    data = (0.2 * np.sin(2 * np.pi * 220.0 * np.arange(n) / file_sr)).astype(np.float32)
    wav = tmp_path / "cancel.wav"
    sf_mod.write(str(wav), data, file_sr)

    monkeypatch.setattr(ai_audio_service, "STEM_LOAD_CHUNK_SECONDS", 2)

    fallback_used = {"hit": False}
    orig_load = torchaudio.load

    def _spy_load(*a, **k):
        fallback_used["hit"] = True
        return orig_load(*a, **k)

    monkeypatch.setattr(torchaudio, "load", _spy_load)

    with pytest.raises(RuntimeError, match="abgebrochen"):
        ai_audio_service._load_audio_for_stem_separation(
            wav, torchaudio, target_sr=44100, should_stop=lambda: True,
        )
    assert fallback_used["hit"] is False


def test_stem_diagnostic_chunk_limit_raises_before_partial_success(monkeypatch):
    from services import ai_audio_service

    monkeypatch.setenv("PB_STEM_MAX_CHUNKS", "2")

    with pytest.raises(RuntimeError, match="Diagnose-Limit erreicht"):
        ai_audio_service._raise_if_stem_diagnostic_chunk_limit_reached(
            chunk_index=2,
            num_chunks=403,
        )


def test_stem_diagnostic_chunk_limit_ignores_invalid_values(monkeypatch):
    from services import ai_audio_service

    monkeypatch.setenv("PB_STEM_MAX_CHUNKS", "abc")

    ai_audio_service._raise_if_stem_diagnostic_chunk_limit_reached(
        chunk_index=402,
        num_chunks=403,
    )
