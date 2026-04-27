"""B-072 + B-066 + B-092-confirm Batch-4 regression tests.

Source-inspection-basiert + funktionale Detection-Tests fuer B-066.
"""

from __future__ import annotations

import inspect


# ---------------------------------------------------------------------------
# B-072: StemSeparator nutzt track_lock
# ---------------------------------------------------------------------------


def test_stem_separator_uses_track_lock() -> None:
    """B-072: ``separate_and_store`` muss den ``track_lock``-ContextManager
    nutzen — sonst race bei parallelen Calls auf denselben Track."""
    from services.ai_audio_service import StemSeparator

    src = inspect.getsource(StemSeparator.separate_and_store)
    assert "track_lock" in src, (
        "B-072: separate_and_store nutzt track_lock nicht — "
        "doppelte Demucs-Runs auf gleichem Track moeglich."
    )


# ---------------------------------------------------------------------------
# B-066: BaseAnalysisWorker erkennt Fallback-Results
# ---------------------------------------------------------------------------


def test_base_analysis_worker_has_fallback_detection() -> None:
    """B-066: ``BaseAnalysisWorker`` muss ``_is_fallback_result`` und
    ``_fallback_reason`` als Helper haben."""
    from workers.audio_analysis import BaseAnalysisWorker

    assert hasattr(BaseAnalysisWorker, "_is_fallback_result")
    assert hasattr(BaseAnalysisWorker, "_fallback_reason")


def test_base_analysis_worker_run_blocks_fallback_db_write() -> None:
    """B-066: ``run()`` muss ``_is_fallback_result(result)`` checken
    und bei True einen RuntimeError raisen — sonst landet der Default-
    Wert silent in der DB."""
    from workers.audio_analysis import BaseAnalysisWorker

    src = inspect.getsource(BaseAnalysisWorker.run)
    assert "_is_fallback_result" in src, (
        "B-066: run() prueft nicht auf Fallback-Result."
    )
    assert "RuntimeError" in src or "raise" in src


def test_is_fallback_result_detects_explicit_flag() -> None:
    """B-066: explicit ``is_fallback=True`` muss erkannt werden."""
    from workers.audio_analysis import BaseAnalysisWorker

    class _R:
        is_fallback = True
    assert BaseAnalysisWorker._is_fallback_result(_R()) is True


def test_is_fallback_result_detects_method_fallback() -> None:
    """B-066: ``method='fallback'`` (KeyResult-Pattern) wird erkannt."""
    from workers.audio_analysis import BaseAnalysisWorker

    class _R:
        method = "fallback"
    assert BaseAnalysisWorker._is_fallback_result(_R()) is True


def test_is_fallback_result_detects_classify_pattern() -> None:
    """B-066: ClassifyResult mit ``confidence=0.0`` und description-Prefix
    wird erkannt."""
    from workers.audio_analysis import BaseAnalysisWorker

    class _R:
        confidence = 0.0
        description = "Klassifikation nicht moeglich: librosa fehlt"
    assert BaseAnalysisWorker._is_fallback_result(_R()) is True


def test_is_fallback_result_passes_valid_result() -> None:
    """B-066: ein normales Result darf NICHT als Fallback erkannt werden."""
    from workers.audio_analysis import BaseAnalysisWorker

    class _R:
        is_fallback = False
        method = "librosa"
        confidence = 0.85
        description = "Standard-Analyse"
    assert BaseAnalysisWorker._is_fallback_result(_R()) is False


def test_lufs_result_has_fallback_flag() -> None:
    """B-066: ``LUFSResult`` muss das ``is_fallback``-Feld haben (es
    war eines der drei betroffenen Services)."""
    from services.lufs_service import LUFSResult

    # Default: is_fallback=False
    r = LUFSResult(
        integrated=-10.0, short_term_max=-7.0, loudness_range=5.0, true_peak=-1.0,
    )
    assert r.is_fallback is False
    # Mit Flag
    r2 = LUFSResult(
        integrated=-14.0, short_term_max=-10.0, loudness_range=8.0, true_peak=-1.0,
        is_fallback=True, fallback_reason="FFmpeg fehlt",
    )
    assert r2.is_fallback is True
    assert r2.fallback_reason == "FFmpeg fehlt"


# ---------------------------------------------------------------------------
# B-092: set_project hat keinen toten _proxied-Block mehr
# ---------------------------------------------------------------------------


def test_set_project_has_no_dead_proxied_check() -> None:
    """B-092 (fixed-by B-133+B-134): ``set_project`` darf nicht mehr
    ``hasattr(engine, '_proxied')`` als ausfuehrbare Code-Zeile haben.
    Erwaehnungen im Docstring/Kommentar (z.B. der Erklaerungs-Block
    "B-133 + B-134: alter dead-code Block entfernt — engine._proxied
    existierte nie") sind erlaubt.
    """
    import inspect as _inspect

    from database import session as _ses

    src = _inspect.getsource(_ses.set_project)
    # Filtere reine Code-Zeilen — Docstring + Inline-Kommentare ueberspringen.
    in_docstring = False
    code_lines: list[str] = []
    for line in src.splitlines():
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert "hasattr(engine, '_proxied')" not in code, (
        "B-092: ``hasattr(engine, '_proxied')`` ist Dead-Code (Attribut "
        "existiert nie) — der if-Block muss entfernt sein."
    )
    assert "time.sleep" not in code, (
        "B-092: ``time.sleep(0.1)`` als M-42-Hack darf nicht mehr im "
        "set_project-Code stehen."
    )
