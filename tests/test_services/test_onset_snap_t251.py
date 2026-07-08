"""NEUBAU-VOLLINTEGRATION T2.5.1 (FR-S1-1 / PIPE-016):
cut_snapper verdrahtet + Onset-Analyse ohne 1800s-Kappung.
"""
import numpy as np

from services.onset_rhythm_service import (
    MAX_DURATION_SEC,
    OnsetRhythmService,
    PercussiveOnset,
    RhythmAnalysis,
)
from services.pacing.cut_snapper import snap_to_onset


class TestLongChunkedWrapper:
    """B-359/PIPE-016: _analyze_long_chunked schneidet HIER pro Chunk und
    ruft analyze() je Slice (RAM-sicher), statt structure_segments an
    analyze() zu reichen (das chunkt nicht). Onsets werden auf globale Zeit
    zurueckgerechnet."""

    def test_chunks_slice_audio_ram_bounded(self, monkeypatch):
        svc = OnsetRhythmService()
        seen_lengths: list[int] = []

        def fake_analyze(y, sr, beats, drums_y=None, structure_segments=None):
            # analyze() bekommt echte Slices — kein structure_segments mehr.
            assert structure_segments is None
            seen_lengths.append(len(y))
            return RhythmAnalysis()

        monkeypatch.setattr(svc, "analyze", fake_analyze)
        sr = 1000
        total_sec = int(MAX_DURATION_SEC * 2.5)  # 2.5 Chunks -> 3 Analysen
        y = np.zeros(total_sec * sr, dtype=np.float32)

        svc._analyze_long_chunked(y, sr, beats=[], chunk_sec=float(MAX_DURATION_SEC))

        assert len(seen_lengths) == 3
        # KEIN Slice groesser als ein Chunk (RAM-Grenze = alter B-359-Cap).
        assert max(seen_lengths) <= int(MAX_DURATION_SEC * sr)

    def test_onsets_offset_to_global_time(self, monkeypatch):
        """Onsets aus Chunk 2 muessen auf globale Zeit (+ Chunk-Start)
        zurueckgerechnet werden."""
        svc = OnsetRhythmService()
        calls = {"i": 0}

        def fake_analyze(y, sr, beats, drums_y=None, structure_segments=None):
            calls["i"] += 1
            # Jeder Chunk liefert einen Kick bei chunk-relativer Zeit 5.0s.
            return RhythmAnalysis(onsets_kick=[PercussiveOnset(time=5.0, strength=1.0)])

        monkeypatch.setattr(svc, "analyze", fake_analyze)
        sr = 1000
        total_sec = int(MAX_DURATION_SEC * 2)  # exakt 2 Chunks
        y = np.zeros(total_sec * sr, dtype=np.float32)

        result = svc._analyze_long_chunked(y, sr, beats=[], chunk_sec=float(MAX_DURATION_SEC))

        times = sorted(o.time for o in result.onsets_kick)
        assert times == [5.0, MAX_DURATION_SEC + 5.0]

    def test_short_audio_single_analyze(self, monkeypatch):
        svc = OnsetRhythmService()
        calls = {"n": 0}

        def fake_analyze(y, sr, beats, drums_y=None, structure_segments=None):
            calls["n"] += 1
            return RhythmAnalysis()

        monkeypatch.setattr(svc, "analyze", fake_analyze)
        sr = 1000
        y = np.zeros(100 * sr, dtype=np.float32)  # << Cap -> 1 Chunk
        svc._analyze_long_chunked(y, sr, beats=[], chunk_sec=float(MAX_DURATION_SEC))
        assert calls["n"] == 1


class TestSnapGuarantee:
    def test_snap_within_50ms_only(self):
        onsets = [10.03, 20.5]
        assert snap_to_onset(10.0, onsets, max_shift_ms=50.0) == 10.03  # 30ms
        assert snap_to_onset(20.0, onsets, max_shift_ms=50.0) == 20.0   # 500ms -> bleibt

    def test_snap_never_exceeds_beat_sync_tolerance(self):
        """50ms Snap-Fenster < 70ms Beat-Sync-Messfenster (SCHNITT-Garantie)."""
        rng = np.random.default_rng(1)
        beats = np.arange(0, 60, 0.44)
        onsets = beats + rng.uniform(-0.05, 0.05, size=beats.size)
        for b in beats[10:20]:
            snapped = snap_to_onset(float(b), onsets, max_shift_ms=50.0)
            assert abs(snapped - b) <= 0.0501
