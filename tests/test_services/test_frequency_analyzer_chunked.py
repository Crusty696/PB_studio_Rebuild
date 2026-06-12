"""B-501: FrequencyAnalyzer Chunked-STFT Tests (CRF-004).

Abgedeckt:
  (a) Block-Zusammenbau: synthetisches Signal ueber mehrere Bloecke →
      Laengen korrekt, keine Diskontinuitaet an Blockgrenzen bei
      stationaerem Signal (max diff < Schwelle).
  (a2) Normalisierung ist GLOBAL, nicht pro Block (Amplituden-Stufe bleibt
       als Stufe sichtbar statt pro Block auf 1.0 hochskaliert).
  (b) Kurzes Signal (≤ BLOCK_SEC) nutzt Single-Pass: genau 1 librosa.load
      ohne offset/duration.
  (c) librosa.beat.beat_track wird nie aufgerufen (totes Beatgrid entfernt);
      Ergebnis enthaelt keine bpm/beat_positions-Keys mehr.

Datei-IO ist komplett gemockt: librosa.load-Fake respektiert offset/duration
auf einem numpy-Signal, librosa.get_duration liefert die synthetische Dauer.
STFT/fft_frequencies laufen echt (librosa).
"""

import numpy as np
import pytest

import services.ai_audio_service as svc
from services.ai_audio_service import FrequencyAnalyzer

SR = FrequencyAnalyzer.SR  # 22050


def _sine(duration_sec: float, freq: float = 440.0, amp: float = 0.8) -> np.ndarray:
    t = np.arange(int(round(duration_sec * SR)), dtype=np.float64) / SR
    return (amp * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


class _FakeAudioFile:
    """Mockt librosa.load/get_duration auf einem in-memory numpy-Signal."""

    def __init__(self, signal: np.ndarray):
        self.signal = signal
        self.duration = len(signal) / SR
        self.load_calls: list[dict] = []

    def fake_load(self, path, sr=None, mono=True, offset=0.0, duration=None,
                  **kwargs):
        self.load_calls.append(
            {"path": path, "sr": sr, "mono": mono, "offset": offset,
             "duration": duration}
        )
        assert sr == SR, f"Unerwartete Sample-Rate: {sr}"
        start = int(round(offset * SR))
        if duration is None:
            end = len(self.signal)
        else:
            end = min(len(self.signal), start + int(round(duration * SR)))
        return self.signal[start:end].copy(), SR

    def fake_get_duration(self, *, path=None, **kwargs):
        return self.duration


@pytest.fixture
def beat_track_guard(monkeypatch):
    """beat_track-Spy: zaehlt Aufrufe (B-501: muss 0 bleiben)."""
    calls = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return 120.0, np.array([])

    monkeypatch.setattr(svc.librosa.beat, "beat_track", _spy)
    return calls


def _patch_io(monkeypatch, fake: _FakeAudioFile):
    monkeypatch.setattr(svc.librosa, "load", fake.fake_load)
    monkeypatch.setattr(svc.librosa, "get_duration", fake.fake_get_duration)


# ---------------------------------------------------------------------------
# (a) Block-Zusammenbau + Kontinuitaet an Blockgrenzen
# ---------------------------------------------------------------------------

class TestChunkedAssembly:
    def test_chunked_path_used_and_lengths_correct(self, monkeypatch, beat_track_guard):
        """25s-Signal mit BLOCK_SEC=10 → 3 Bloecke, Frame-Anzahl wie Single-Pass-Raster."""
        monkeypatch.setattr(FrequencyAnalyzer, "BLOCK_SEC", 10.0)
        fake = _FakeAudioFile(_sine(25.0))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("fake.wav")

        # 3 Block-Loads mit offsets 0/10/20
        offsets = [c["offset"] for c in fake.load_calls]
        assert offsets == [0.0, 10.0, 20.0], f"Block-Offsets falsch: {offsets}"
        assert all(c["duration"] == 10.0 for c in fake.load_calls)

        # Frame-Anzahl: globales Hop-Raster (center=False):
        # 1 + (L - N_FFT) // HOP
        total = len(fake.signal)
        expected = 1 + (total - FrequencyAnalyzer.N_FFT) // FrequencyAnalyzer.HOP_LENGTH
        assert result["num_samples"] == expected, (
            f"num_samples={result['num_samples']}, erwartet={expected}"
        )
        assert len(result["band_low"]) == expected
        assert len(result["band_mid"]) == expected
        assert len(result["band_high"]) == expected
        assert result["duration"] == 25.0

    def test_no_discontinuity_at_block_boundaries(self, monkeypatch, beat_track_guard):
        """Stationaerer Sinus → benachbarte Frame-Werte ueberall nahezu gleich."""
        monkeypatch.setattr(FrequencyAnalyzer, "BLOCK_SEC", 10.0)
        fake = _FakeAudioFile(_sine(25.0, freq=440.0, amp=0.8))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("fake.wav")

        band_mid = np.asarray(result["band_mid"], dtype=np.float64)
        # 440 Hz liegt im Mid-Band → nach globaler Normalisierung ~1.0 ueberall
        assert band_mid.max() == pytest.approx(1.0, abs=1e-3)
        max_diff = float(np.max(np.abs(np.diff(band_mid))))
        assert max_diff < 0.01, (
            f"Diskontinuitaet an Blockgrenze: max benachbarte Differenz {max_diff:.6f}"
        )

    def test_normalization_is_global_not_per_block(self, monkeypatch, beat_track_guard):
        """Amplituden-Stufe (0.1 → 1.0) bleibt nach Normalisierung erhalten.

        Bei (fehlerhafter) Pro-Block-Normalisierung waere Block 1 (nur leise
        Anteile) auf ~1.0 hochskaliert.
        """
        monkeypatch.setattr(FrequencyAnalyzer, "BLOCK_SEC", 10.0)
        quiet = _sine(12.0, amp=0.1)
        loud = _sine(13.0, amp=1.0)
        fake = _FakeAudioFile(np.concatenate([quiet, loud]))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("fake.wav")
        band_mid = np.asarray(result["band_mid"], dtype=np.float64)

        frames_per_sec = SR / FrequencyAnalyzer.HOP_LENGTH  # ~43
        quiet_region = band_mid[10:int(10.0 * frames_per_sec)]   # sicher in [0..10s] = Block 1
        loud_region = band_mid[int(15.0 * frames_per_sec):int(22.0 * frames_per_sec)]

        # Verhaeltnis-Check statt Absolutwerte: Der Amplituden-Sprung bei 12s
        # erzeugt einen Breitband-Splash-Frame, der zum globalen Peak (1.0)
        # wird — die stationaeren Regionen liegen daher beide unter 1.0.
        # Entscheidend: quiet/loud ≈ 0.1 (global normalisiert). Bei
        # (fehlerhafter) Pro-Block-Normalisierung waere das Verhaeltnis ≈ 1.0.
        ratio = quiet_region.mean() / loud_region.mean()
        assert 0.05 < ratio < 0.3, (
            f"Pro-Block-Normalisierung erkannt: quiet/loud-Ratio={ratio:.3f} "
            f"(erwartet ~0.1; bei Block-Normalisierung ~1.0)"
        )


# ---------------------------------------------------------------------------
# (b) Kurzes Signal → Single-Pass
# ---------------------------------------------------------------------------

class TestSinglePassShortSignal:
    def test_short_signal_uses_single_pass(self, monkeypatch, beat_track_guard):
        fake = _FakeAudioFile(_sine(5.0))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("short.wav")

        assert len(fake.load_calls) == 1, (
            f"Single-Pass erwartet (1 load), bekam {len(fake.load_calls)}"
        )
        call = fake.load_calls[0]
        # Single-Pass laedt ohne offset/duration (Full-Load der kurzen Datei)
        assert call["offset"] == 0.0
        assert call["duration"] is None
        assert result["num_samples"] == len(result["band_low"])
        assert result["duration"] == 5.0

    def test_default_block_sec_is_600(self):
        assert FrequencyAnalyzer.BLOCK_SEC == 600.0


# ---------------------------------------------------------------------------
# (c) beat_track tot + Result-Kontrakt
# ---------------------------------------------------------------------------

class TestBeatTrackRemoved:
    def test_beat_track_never_called_short(self, monkeypatch, beat_track_guard):
        fake = _FakeAudioFile(_sine(5.0))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("short.wav")

        assert beat_track_guard == [], "librosa.beat.beat_track wurde aufgerufen (B-501)"
        assert "bpm" not in result
        assert "beat_positions" not in result

    def test_beat_track_never_called_chunked(self, monkeypatch, beat_track_guard):
        monkeypatch.setattr(FrequencyAnalyzer, "BLOCK_SEC", 10.0)
        fake = _FakeAudioFile(_sine(25.0))
        _patch_io(monkeypatch, fake)

        result = FrequencyAnalyzer().analyze("long.wav")

        assert beat_track_guard == [], "librosa.beat.beat_track wurde aufgerufen (B-501)"
        assert "bpm" not in result
        assert "beat_positions" not in result
