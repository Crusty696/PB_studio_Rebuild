"""Smoke-Tests fuer SubtrackDetector mit synthetisch erzeugtem Audio.

Echte F-Measure-Tests gegen annotierte DJ-Mixes laufen separat
(siehe scripts/build_test_fixture.py + tests/data/), das ist hier
ausser Scope. Hier nur:
- Detector kann synthetisches Audio verarbeiten
- Fallback (1 Segment) wird korrekt ausgeloest
- Fusion-Gewichte werden re-normalisiert wenn Stems fehlen
- Output-Schema validiert sauber
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


_HAS_LIBROSA = importlib.util.find_spec("librosa") is not None
_HAS_SOUNDFILE = importlib.util.find_spec("soundfile") is not None


HASH64 = "a" * 64
SR = 22050  # geringere SR fuer schnellere Tests


@pytest.fixture
def synth_drone_wav(tmp_path: Path) -> Path:
    """30 Sekunden Sinus-Drone bei 220 Hz — kein echter Mix-Wechsel
    erwartet, deshalb Fallback (1 Segment) sollte greifen."""
    if not (_HAS_LIBROSA and _HAS_SOUNDFILE):
        pytest.skip("librosa/soundfile nicht installiert")
    import soundfile as sf
    duration = 30.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 220 * t).astype("float32")
    out = tmp_path / "drone.wav"
    sf.write(str(out), y, SR)
    return out


@pytest.fixture
def synth_two_section_wav(tmp_path: Path) -> Path:
    """120 Sekunden: 60 s 220 Hz Sinus + 60 s 880 Hz + Noise.

    Das ist ein abrupter Wechsel — Detector SOLLTE eine Boundary
    nahe der 60-s-Marke finden. Aber wir testen das nicht hart hier
    (das ist die Aufgabe des annotierten F-Measure-Tests). Smoke-Test
    nur dass nicht crasht.
    """
    if not (_HAS_LIBROSA and _HAS_SOUNDFILE):
        pytest.skip("librosa/soundfile nicht installiert")
    import soundfile as sf
    half = 60.0
    t1 = np.linspace(0, half, int(SR * half), endpoint=False)
    t2 = np.linspace(0, half, int(SR * half), endpoint=False)
    y1 = 0.2 * np.sin(2 * np.pi * 220 * t1).astype("float32")
    y2 = (0.2 * np.sin(2 * np.pi * 880 * t2)
          + 0.05 * np.random.randn(t2.size)).astype("float32")
    y = np.concatenate([y1, y2])
    out = tmp_path / "two_section.wav"
    sf.write(str(out), y, SR)
    return out


@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_drone_falls_back_to_single_segment(synth_drone_wav: Path):
    """Konstanter Drone hat keine Boundary → Fallback erwartet."""
    from services.brain_v3.audio.subtrack_detector import SubtrackDetector
    det = SubtrackDetector()
    result = det.detect(synth_drone_wav, audio_hash=HASH64)
    assert result.audio_hash == HASH64
    assert result.duration_seconds == pytest.approx(30.0, abs=1.0)
    # Ohne Wechsel: Fallback (1 Segment, fallback_used=True)
    assert result.n_segments == 1
    assert result.fallback_used is True
    seg = result.segments[0]
    assert seg.start_time == 0.0
    assert seg.end_time == pytest.approx(result.duration_seconds, abs=0.5)


@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_two_section_does_not_crash(synth_two_section_wav: Path):
    """Mix mit Wechsel: Smoke-Test dass Detector durchlaeuft.
    F-Measure-Validierung ist separater Test mit annotierten Mixes."""
    from services.brain_v3.audio.subtrack_detector import SubtrackDetector
    det = SubtrackDetector()
    result = det.detect(synth_two_section_wav, audio_hash=HASH64)
    assert result.duration_seconds == pytest.approx(120.0, abs=1.0)
    assert result.n_segments >= 1  # mindestens Fallback


def test_effective_weights_renormalize_without_stems():
    from services.brain_v3.audio.subtrack_detector import SubtrackDetector
    det = SubtrackDetector()
    # Mit Stems: original
    w_with = det._effective_weights(stems_used=True)
    assert w_with == {"foote": 0.35, "stem": 0.30, "tempo": 0.20, "spectral": 0.15}
    # Ohne Stems: stem=0, andere skaliert auf Summe 1
    w_without = det._effective_weights(stems_used=False)
    assert w_without["stem"] == 0.0
    assert sum(v for k, v in w_without.items() if k != "stem") == pytest.approx(1.0)
    # Verhaeltnis foote:tempo:spectral bleibt gleich
    assert w_without["foote"] / w_without["tempo"] == pytest.approx(0.35 / 0.20)


def test_normalize_zero_array_returns_zeros():
    from services.brain_v3.audio.subtrack_detector import SubtrackDetector
    out = SubtrackDetector._normalize(np.zeros(10))
    assert np.all(out == 0)


def test_resize_to_lengths():
    from services.brain_v3.audio.subtrack_detector import SubtrackDetector
    src = np.array([0.0, 1.0, 0.0, 1.0])
    out = SubtrackDetector._resize_to(src, 8)
    assert out.size == 8
    # Linear interp: zwischen 0 und 1 muss Mittelwert ~0.5 ergeben
    assert out[1] == pytest.approx(0.4286, abs=0.01)
