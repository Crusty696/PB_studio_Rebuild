"""NEUBAU-VOLLINTEGRATION T2.5.1 (FR-S1-1 / PIPE-016):
cut_snapper verdrahtet + Onset-Analyse ohne 1800s-Kappung.
"""
import numpy as np

from services.onset_rhythm_service import MAX_DURATION_SEC, OnsetRhythmService
from services.pacing.cut_snapper import snap_to_onset


class TestLongChunkedWrapper:
    def test_segments_cover_full_duration(self, monkeypatch):
        svc = OnsetRhythmService()
        captured = {}

        def fake_analyze(y, sr, beats, drums_y=None, structure_segments=None):
            captured["segments"] = structure_segments
            return "ANALYSIS"

        monkeypatch.setattr(svc, "analyze", fake_analyze)
        sr = 1000
        total_sec = int(MAX_DURATION_SEC * 2.5)  # 2.5 Chunks
        y = np.zeros(total_sec * sr, dtype=np.float32)

        result = svc._analyze_long_chunked(y, sr, beats=[], chunk_sec=float(MAX_DURATION_SEC))

        assert result == "ANALYSIS"
        segs = captured["segments"]
        assert len(segs) == 3
        assert segs[0][0] == 0.0
        assert abs(segs[-1][1] - total_sec) < 1e-6  # Ende = Gesamtlaenge
        # lueckenlos + monoton
        for (a0, a1), (b0, b1) in zip(segs, segs[1:]):
            assert abs(a1 - b0) < 1e-6

    def test_short_audio_single_segment(self, monkeypatch):
        svc = OnsetRhythmService()
        captured = {}
        monkeypatch.setattr(
            svc, "analyze",
            lambda y, sr, beats, drums_y=None, structure_segments=None:
            captured.update(segments=structure_segments) or "A")
        sr = 1000
        y = np.zeros(100 * sr, dtype=np.float32)
        svc._analyze_long_chunked(y, sr, beats=[], chunk_sec=float(MAX_DURATION_SEC))
        assert len(captured["segments"]) == 1


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
