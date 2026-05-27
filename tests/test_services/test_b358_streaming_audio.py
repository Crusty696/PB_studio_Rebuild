"""B-358: Beat-Analyse laedt lange Dateien nicht mehr komplett in RAM.

- ``_compute_energy_per_beat_streaming`` liefert dieselbe normalisierte
  Per-Beat-RMS-Liste wie die Full-Array-Methode (Block-Akkumulation korrekt).
- ``_analyze_chunked`` laedt jeden Chunk einzeln via ``librosa.load`` mit
  offset/duration statt aus einem komplett geladenen Signal zu slicen.
"""
from __future__ import annotations

import numpy as np
import soundfile as sf

from services import beat_analysis_service
from services.audio_constants import DEFAULT_SR
from services.beat_analysis_service import BeatAnalysisService


def _write_varying_wav(path, seconds: float, sr: int) -> None:
    t = np.linspace(0.0, seconds, int(seconds * sr), endpoint=False)
    # Amplitude moduliert ueber die Zeit -> nicht-konstante Energie pro Beat.
    amp = 0.1 + 0.9 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t))
    y = (amp * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    sf.write(str(path), y, sr, subtype="FLOAT")


def test_streaming_energy_matches_full_array(tmp_path, monkeypatch):
    import librosa

    sr = DEFAULT_SR
    seconds = 20.0
    wav = tmp_path / "tone.wav"
    _write_varying_wav(wav, seconds, sr)

    y_full, _ = librosa.load(str(wav), sr=sr, mono=True)
    duration = len(y_full) / sr
    beats = [round(b, 4) for b in np.arange(0.0, duration - 0.5, 0.5).tolist()]

    legacy = BeatAnalysisService._compute_energy_per_beat(
        y_full, sr, beats, duration
    )

    # Kleine Bloecke erzwingen -> Akkumulation ueber mehrere Disk-Reads.
    monkeypatch.setattr(beat_analysis_service, "CHUNK_DURATION_SEC", 3.0)
    streaming = BeatAnalysisService._compute_energy_per_beat_streaming(
        str(wav), sr, beats, duration
    )

    assert len(streaming) == len(legacy)
    assert streaming == legacy


def test_streaming_energy_edge_cases(tmp_path):
    sr = DEFAULT_SR
    wav = tmp_path / "tone.wav"
    _write_varying_wav(wav, 2.0, sr)
    assert BeatAnalysisService._compute_energy_per_beat_streaming(str(wav), sr, [], 2.0) == []
    assert BeatAnalysisService._compute_energy_per_beat_streaming(str(wav), sr, [0.5], 2.0) == []


def test_analyze_chunked_streams_per_chunk_from_disk(tmp_path, monkeypatch):
    """Jeder Chunk wird einzeln mit offset/duration geladen — kein Full-Load."""
    sr = DEFAULT_SR
    wav = tmp_path / "long.wav"
    # Echte (kurze) Datei; total_duration wird kuenstlich lang gesetzt.
    _write_varying_wav(wav, 1.0, sr)

    monkeypatch.setattr(beat_analysis_service, "CHUNK_DURATION_SEC", 600.0)
    monkeypatch.setattr(beat_analysis_service, "CHUNK_OVERLAP_SEC", 0.0)

    load_calls: list[dict] = []

    def _fake_load(path, sr=None, mono=None, offset=None, duration=None):
        load_calls.append({"offset": offset, "duration": duration})
        n = int(round((duration or 0.0) * sr))
        return np.zeros(n, dtype=np.float32), sr

    import librosa
    monkeypatch.setattr(librosa, "load", _fake_load)
    monkeypatch.setattr(sf, "write", lambda *a, **k: None)

    BeatAnalysisService._instance = None
    svc = BeatAnalysisService()
    try:
        monkeypatch.setattr(svc, "_ensure_model", lambda: None)
        # Modell gibt pro Chunk zwei Beats relativ zum Chunk-Start zurueck.
        svc._model = lambda p: (np.array([1.0, 2.0]), np.array([1.0]))

        total_duration = 1500.0  # > 2 Chunks bei 600s
        beats, downbeats = svc._analyze_chunked(str(wav), total_duration, sr)
    finally:
        BeatAnalysisService._instance = None

    # 1500s / 600s (ohne Overlap) -> 3 Chunks -> 3 einzelne Disk-Loads.
    assert len(load_calls) == 3
    # Jeder Load ist offset/duration-bounded (kein Full-Load).
    assert all(c["offset"] is not None and c["duration"] is not None for c in load_calls)
    offsets = [c["offset"] for c in load_calls]
    assert offsets == sorted(offsets) and offsets[0] == 0.0 and offsets[-1] > 0.0
    assert len(beats) > 0
