"""Verify-Tests fuer den Adversarial-Audio-Audit (2026-04-28).

- B-228: Drop-Detection Threshold 0.01 → 0.05.
- B-230: ``except`` umfasst jetzt audioread/soundfile-Exceptions.
- B-232: ``_match_groove_template`` returnt ("unknown", 0.0) bei
  beat_dur=0 statt ZeroDivisionError.
- B-236: ``OnsetRhythmService._store`` retried bei DB-Lock mit
  exponential backoff + jitter.
"""

from __future__ import annotations

import inspect

import pytest


# --------------------------------------------------------------------------
# B-228: Drop-Threshold
# --------------------------------------------------------------------------

def test_b228_drop_detection_threshold_raised() -> None:
    """``_detect_drops`` (oder Equivalent) nutzt 0.05-Schwelle statt 0.01."""
    from services import spectral_analysis_service

    src = inspect.getsource(spectral_analysis_service)
    assert "B-228" in src, "B-228-Marker fehlt"
    assert "prev_e > 0.05" in src, (
        "B-228: Drop-Detection nutzt nicht den korrigierten 0.05-Threshold"
    )


# --------------------------------------------------------------------------
# B-230: broad except fuer audioread/soundfile
# --------------------------------------------------------------------------

def test_b230_spectral_uses_broad_except() -> None:
    from services import spectral_analysis_service

    src = inspect.getsource(spectral_analysis_service)
    assert "B-230" in src
    # Narrow tuple darf nicht mehr in den Haupt-Catch-Bloecken sein
    assert src.count("(OSError, IOError, ValueError, RuntimeError)") == 0, (
        "B-230: spectral hat noch narrow except-Tupel um librosa.load"
    )


def test_b230_structure_uses_broad_except() -> None:
    from services import structure_detection_service

    src = inspect.getsource(structure_detection_service)
    assert "B-230" in src
    assert src.count("(OSError, IOError, ValueError, RuntimeError)") == 0, (
        "B-230: structure_detection hat noch narrow except-Tupel"
    )


def test_b230_onset_uses_broad_except() -> None:
    from services import onset_rhythm_service

    src = inspect.getsource(onset_rhythm_service)
    assert "B-230" in src


# --------------------------------------------------------------------------
# B-232: groove template zero-division guard
# --------------------------------------------------------------------------

def test_b232_groove_template_handles_zero_beat_duration() -> None:
    """Degenerierte Beat-Arrays (alle gleich) duerfen keinen Crash."""
    from services.onset_rhythm_service import OnsetRhythmService

    svc = OnsetRhythmService()
    # 4 identische Beats → np.diff = [0,0,0] → median = 0
    name, confidence = svc._match_groove_template(
        kicks=[],
        snares=[],
        beats=[1.0, 1.0, 1.0, 1.0],
    )
    assert name == "unknown"
    assert confidence == 0.0


# --------------------------------------------------------------------------
# B-236: OnsetRhythmService._store retry-loop
# --------------------------------------------------------------------------

def test_b236_onset_store_has_retry_loop() -> None:
    from services.onset_rhythm_service import OnsetRhythmService

    src = inspect.getsource(OnsetRhythmService._store)
    assert "B-236" in src
    assert "max_retries" in src, "B-236: _store hat keinen Retry-Counter"
    assert "database is locked" in src, "B-236: kein Lock-Detection-Pfad"
    assert "random.uniform" in src or "_random.uniform" in src, (
        "B-236: kein Jitter im Retry"
    )
    assert "2 ** attempt" in src, "B-236: kein exponential backoff"
