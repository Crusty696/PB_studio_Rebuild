"""Verify-Tests fuer B-062 und B-074.

- B-062: ``BeatAnalysisService._analyze_with_audio`` returnt
  ``(dict, y, sr)`` als Tupel statt y/sr in den Singleton zu schreiben
  (``_last_y``/``_last_sr`` sind entfernt).
- B-074: ``AutoDucker.create_ducked_audio`` akzeptiert ``should_stop``
  und reicht es an die FFmpeg-Konvertierung durch (``_run_ffmpeg_cancellable``).
  ``AutoDuckingWorker.run`` reicht ``self.should_stop`` durch.
"""

from __future__ import annotations

import inspect

import pytest


# --------------------------------------------------------------------------
# B-062: _analyze_with_audio Tupel-Return
# --------------------------------------------------------------------------

def test_b062_analyze_with_audio_returns_tuple() -> None:
    """``_analyze_with_audio`` ist als private Helper definiert und
    returnt das Tupel ``(dict, y, sr)``."""
    from services.beat_analysis_service import BeatAnalysisService

    assert hasattr(BeatAnalysisService, "_analyze_with_audio"), (
        "B-062: _analyze_with_audio fehlt"
    )
    src = inspect.getsource(BeatAnalysisService._analyze_with_audio)
    assert "B-062" in src
    assert "return result, y, sr" in src, (
        "B-062: _analyze_with_audio muss Tupel returnen"
    )


def test_b062_no_more_last_y_attributes() -> None:
    """Singleton hat keine ``_last_y`` / ``_last_sr`` Attribute mehr —
    diese waren die Quelle des Race."""
    from services.beat_analysis_service import BeatAnalysisService

    # Reset fuer dezidierten Test (Singleton)
    BeatAnalysisService._instance = None
    svc = BeatAnalysisService()
    try:
        assert not hasattr(svc, "_last_y") or svc.__dict__.get("_last_y") is None
        assert not hasattr(svc, "_last_sr") or svc.__dict__.get("_last_sr") is None
        # Genauer: die Attribute werden nicht mehr im __init__ gesetzt
        # (frueher: ``self._last_y = None``)
        assert "_last_y" not in svc.__dict__, (
            "B-062: _last_y existiert noch im Instance-Dict — Race-Quelle"
        )
        assert "_last_sr" not in svc.__dict__, (
            "B-062: _last_sr existiert noch im Instance-Dict — Race-Quelle"
        )
    finally:
        BeatAnalysisService._instance = None


def test_b062_analyze_is_thin_wrapper() -> None:
    """``analyze()`` ist seit B-062 ein duenner Wrapper um
    ``_analyze_with_audio()`` — sollte keine ``self._last_y =`` Schreibops
    mehr enthalten (Vorkommen in Kommentaren/Docstrings sind erlaubt)."""
    from services.beat_analysis_service import BeatAnalysisService

    src = inspect.getsource(BeatAnalysisService.analyze)
    # Echte Zuweisung (Pattern ``self._last_y =``) darf nicht mehr da sein.
    assert "self._last_y =" not in src, (
        "B-062: analyze() schreibt noch self._last_y — Race nicht behoben"
    )
    assert "self._last_sr =" not in src
    assert "_analyze_with_audio" in src, (
        "B-062: analyze() ruft den Helper nicht"
    )


def test_b062_analyze_and_store_uses_helper() -> None:
    """``analyze_and_store()`` nutzt den neuen Helper und liest y/sr
    nicht mehr aus Instance-State."""
    from services.beat_analysis_service import BeatAnalysisService

    src = inspect.getsource(BeatAnalysisService.analyze_and_store)
    assert "_analyze_with_audio" in src, (
        "B-062: analyze_and_store nutzt nicht den race-freien Helper"
    )
    # Auch hier: nur Reads/Writes pruefen, keine Kommentar-Treffer
    assert "self._last_y =" not in src and "= self._last_y" not in src, (
        "B-062: analyze_and_store liest/schreibt noch self._last_y"
    )


# --------------------------------------------------------------------------
# B-074: AutoDucker should_stop
# --------------------------------------------------------------------------

def test_b074_create_ducked_audio_has_should_stop_param() -> None:
    """``AutoDucker.create_ducked_audio`` akzeptiert ``should_stop``."""
    from services.ai_audio_service import AutoDucker

    sig = inspect.signature(AutoDucker.create_ducked_audio)
    assert "should_stop" in sig.parameters, (
        "B-074: AutoDucker.create_ducked_audio hat kein should_stop-Parameter"
    )


def test_b074_create_ducked_audio_scipy_has_should_stop_param() -> None:
    """``AutoDucker.create_ducked_audio_scipy`` akzeptiert ``should_stop``."""
    from services.ai_audio_service import AutoDucker

    sig = inspect.signature(AutoDucker.create_ducked_audio_scipy)
    assert "should_stop" in sig.parameters


def test_b074_run_ffmpeg_cancellable_helper_exists() -> None:
    """Cancel-faehiger FFmpeg-Helper ist als Module-Funktion verfuegbar."""
    from services import ai_audio_service

    assert hasattr(ai_audio_service, "_run_ffmpeg_cancellable")
    src = inspect.getsource(ai_audio_service._run_ffmpeg_cancellable)
    assert "B-074" in src
    # Watchdog-Pattern muss Popen + terminate haben
    assert "Popen" in src
    assert "terminate" in src


def test_b074_run_ffmpeg_cancellable_falls_back_to_run_when_no_callback() -> None:
    """Ohne ``should_stop`` faellt der Helper auf blockierendes
    ``subprocess.run`` zurueck (alter Pfad bleibt bit-identisch)."""
    from services.ai_audio_service import _run_ffmpeg_cancellable

    # Ein unschuldiger Befehl — wir testen nur den Code-Pfad ohne
    # tatsaechliches FFmpeg.
    rc, stderr = _run_ffmpeg_cancellable(
        ["python", "-c", "import sys; sys.stderr.write('hello'); sys.exit(0)"],
        timeout=5,
        should_stop=None,
    )
    assert rc == 0
    assert "hello" in stderr


def test_b074_auto_ducking_worker_passes_should_stop() -> None:
    """``AutoDuckingWorker.run`` reicht ``self.should_stop`` durch."""
    from workers import audio as audio_workers

    src = inspect.getsource(audio_workers.AutoDuckingWorker.run)
    assert "should_stop=self.should_stop" in src, (
        "B-074: AutoDuckingWorker.run reicht should_stop nicht durch"
    )
