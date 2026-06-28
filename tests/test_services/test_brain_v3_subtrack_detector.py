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
    from services.brain.audio.subtrack_detector import SubtrackDetector
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
    from services.brain.audio.subtrack_detector import SubtrackDetector
    det = SubtrackDetector()
    result = det.detect(synth_two_section_wav, audio_hash=HASH64)
    assert result.duration_seconds == pytest.approx(120.0, abs=1.0)
    assert result.n_segments >= 1  # mindestens Fallback


# ---------------------------------------------------------------------------
# B-510: Foote-Kernel-Vektorisierung — numerische Aequivalenz alt vs. neu
# ---------------------------------------------------------------------------

def _foote_novelty_reference(rec: np.ndarray, kernel_size: int) -> np.ndarray:
    """Alter purer Python-Doppelloop (Stand vor B-510, unveraendert kopiert)."""
    n = rec.shape[0]
    novelty = np.zeros(n)
    k = kernel_size
    if n < 2 * k + 1:
        return novelty
    for i in range(k, n - k):
        tl = rec[i - k:i, i - k:i].mean()
        br = rec[i:i + k, i:i + k].mean()
        tr = rec[i - k:i, i:i + k].mean()
        bl = rec[i:i + k, i - k:i].mean()
        novelty[i] = (tl + br) - (tr + bl)
    return np.clip(novelty, 0, None)


@pytest.fixture
def synth_60s_wav(tmp_path: Path) -> Path:
    """60 Sekunden: 30 s 220 Hz + 30 s 880 Hz + Noise (B-510-Testsignal)."""
    if not (_HAS_LIBROSA and _HAS_SOUNDFILE):
        pytest.skip("librosa/soundfile nicht installiert")
    import soundfile as sf
    half = 30.0
    t = np.linspace(0, half, int(SR * half), endpoint=False)
    rng = np.random.default_rng(7)
    y1 = 0.2 * np.sin(2 * np.pi * 220 * t).astype("float32")
    y2 = (0.2 * np.sin(2 * np.pi * 880 * t)
          + 0.05 * rng.standard_normal(t.size)).astype("float32")
    out = tmp_path / "b510_60s.wav"
    sf.write(str(out), np.concatenate([y1, y2]), SR)
    return out


@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_foote_novelty_vectorized_matches_reference_on_60s_signal(synth_60s_wav: Path):
    """B-510: Vektorisierung (Summed-Area-Table) == alter Loop auf echter
    Recurrence-Matrix eines 60-s-Signals (rtol 1e-5)."""
    import librosa
    from services.brain.audio.subtrack_detector import SubtrackDetector

    y, sr = librosa.load(str(synth_60s_wav), sr=22050, mono=True)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=22050)
    rec = librosa.segment.recurrence_matrix(mfcc, mode="affinity", sym=True)
    n = rec.shape[0]
    kernel_size = min(64, max(4, n // 32))

    new = SubtrackDetector._foote_kernel_novelty(rec, kernel_size=kernel_size)
    ref = _foote_novelty_reference(rec, kernel_size=kernel_size)

    assert new.shape == ref.shape
    # atol faengt SAT-Rundungsrauschen bei Werten ~0 ab (float64-Cumsum)
    assert np.allclose(new, ref, rtol=1e-5, atol=1e-10), (
        f"max abs diff: {np.abs(new - ref).max():.3e}"
    )


def test_foote_novelty_vectorized_matches_reference_random_matrices():
    """B-510: Aequivalenz auch auf groesseren Zufalls-Affinity-Matrizen."""
    from services.brain.audio.subtrack_detector import SubtrackDetector
    rng = np.random.default_rng(123)
    for n, k in [(60, 4), (240, 12), (500, 15)]:
        m = rng.random((n, n))
        rec = (m + m.T) / 2.0  # symmetrisch, [0, 1] — wie affinity
        new = SubtrackDetector._foote_kernel_novelty(rec, kernel_size=k)
        ref = _foote_novelty_reference(rec, kernel_size=k)
        assert np.allclose(new, ref, rtol=1e-5, atol=1e-10), (
            f"n={n}, k={k}: max abs diff {np.abs(new - ref).max():.3e}"
        )


def test_foote_novelty_small_matrix_returns_zeros():
    """Randfall n < 2k+1 bleibt unveraendert (Null-Vektor)."""
    from services.brain.audio.subtrack_detector import SubtrackDetector
    rec = np.ones((5, 5))
    out = SubtrackDetector._foote_kernel_novelty(rec, kernel_size=4)
    assert np.all(out == 0)
    assert out.shape == (5,)


# ---------------------------------------------------------------------------
# B-510: progress_cb + should_stop Hooks
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_detect_progress_cb_called(synth_60s_wav: Path):
    """B-510: progress_cb wird mit (pct, msg) aufgerufen, pct monoton 0..100."""
    from services.brain.audio.subtrack_detector import SubtrackDetector
    calls: list[tuple[int, str]] = []
    det = SubtrackDetector()
    result = det.detect(
        synth_60s_wav, audio_hash=HASH64,
        progress_cb=lambda pct, msg: calls.append((pct, msg)),
    )
    assert result is not None
    assert len(calls) >= 4
    pcts = [c[0] for c in calls]
    assert all(0 <= p <= 100 for p in pcts)
    assert pcts == sorted(pcts), f"Progress nicht monoton: {pcts}"
    assert pcts[-1] == 100


@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_detect_should_stop_aborts_cleanly(synth_60s_wav: Path):
    """B-510: should_stop=True -> sauberer Abbruch, return None, keine Exception."""
    from services.brain.audio.subtrack_detector import SubtrackDetector
    det = SubtrackDetector()
    result = det.detect(synth_60s_wav, audio_hash=HASH64, should_stop=lambda: True)
    assert result is None


@pytest.mark.skipif(not (_HAS_LIBROSA and _HAS_SOUNDFILE),
                    reason="librosa/soundfile nicht installiert")
def test_detect_loads_at_fixed_22050(synth_60s_wav: Path, monkeypatch):
    """B-510: detect() laedt mit fester sr=22050 statt sr=None (nativer SR)."""
    import librosa
    from services.brain.audio import subtrack_detector as mod
    seen = {}
    orig_load = librosa.load

    def spy_load(path, sr=None, mono=True, **kw):
        seen.setdefault("sr", sr)
        return orig_load(path, sr=sr, mono=mono, **kw)

    monkeypatch.setattr(librosa, "load", spy_load)
    det = mod.SubtrackDetector()
    det.detect(synth_60s_wav, audio_hash=HASH64)
    assert seen["sr"] == 22050


def test_effective_weights_renormalize_without_stems():
    from services.brain.audio.subtrack_detector import SubtrackDetector
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
    from services.brain.audio.subtrack_detector import SubtrackDetector
    out = SubtrackDetector._normalize(np.zeros(10))
    assert np.all(out == 0)


def test_resize_to_lengths():
    from services.brain.audio.subtrack_detector import SubtrackDetector
    src = np.array([0.0, 1.0, 0.0, 1.0])
    out = SubtrackDetector._resize_to(src, 8)
    assert out.size == 8
    # Linear interp: zwischen 0 und 1 muss Mittelwert ~0.5 ergeben
    assert out[1] == pytest.approx(0.4286, abs=0.01)
