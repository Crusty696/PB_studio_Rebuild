"""Cycle 6 Export/Render — RED-Tests fuer B-167, B-168, B-169, B-170.

Source-inspection-Tests (kein FFmpeg/DB).
"""
from __future__ import annotations

import inspect


def test_b167_cancel_watch_logs_exceptions():
    """B-167: _cancel_watch (in _run_subprocess_cancellable und _run_ffmpeg)
    muss Exceptions aus cancel_check loggen statt stumm den Watchdog zu killen."""
    from services import export_service

    src1 = inspect.getsource(export_service._run_subprocess_cancellable)
    src2 = inspect.getsource(export_service._run_ffmpeg)

    # Beide Funktionen muessen logger.{warning|error|info} im except-Pfad rufen
    for name, src in (("_run_subprocess_cancellable", src1), ("_run_ffmpeg", src2)):
        # Fragmente "except Exception:" oder "except BaseException:" gefolgt
        # von "return" ohne Logging waeren Bug. Wir suchen ein logger-Call
        # innerhalb des cancel-watch-Blocks.
        watch_idx = src.find("def _cancel_watch")
        assert watch_idx > 0, f"{name}: _cancel_watch fehlt"
        watch_body = src[watch_idx:watch_idx + 1500]
        assert "logger." in watch_body, (
            f"{name}._cancel_watch verschluckt cancel_check-Exceptions stumm (B-167)."
        )


def test_b168_concat_demuxer_rejects_control_chars():
    """B-168: Concat-Demuxer-Path-Sanitizer muss control chars (newline,
    CR, NUL) ablehnen. Sonst Format-Korruption oder Datei-Truncation."""
    from services import export_service

    # Hilfsfunktion muss existieren
    assert hasattr(export_service, "_sanitize_concat_path"), (
        "_sanitize_concat_path muss existieren (B-168)."
    )
    sanitize = export_service._sanitize_concat_path

    # Normaler Pfad: durchlassen, Backslash → Slash, Single-Quote escapen
    assert sanitize(r"C:\videos\clip.mp4") == "C:/videos/clip.mp4"
    assert "'\\''" in sanitize("C:/it's/clip.mp4")

    # Control chars: ablehnen
    import pytest
    for bad in ("a\nb.mp4", "a\rb.mp4", "a\x00b.mp4"):
        with pytest.raises(ValueError):
            sanitize(bad)


def test_b169_filter_complex_uses_script_for_long_graphs():
    """B-169: _export_with_filtergraph muss filter_complex_script nutzen
    bei langen Filtergraphs, sonst Windows-cmdline-Overflow bei 100+ Segmenten."""
    from services import export_service

    src = inspect.getsource(export_service._export_with_filtergraph)
    # Mindestens muss "filter_complex_script" als Zweig vorhanden sein.
    assert "filter_complex_script" in src, (
        "_export_with_filtergraph muss bei langen Filtergraphs auf "
        "-filter_complex_script <datei> ausweichen (B-169)."
    )


def test_b170_run_ffmpeg_terminate_guarded_by_cancelled():
    """B-170: _run_ffmpeg main-loop UND Watchdog muessen vor terminate()
    via cancelled.is_set() guarden, sonst ChildProcessError-Race."""
    from services import export_service

    src = inspect.getsource(export_service._run_ffmpeg)
    # Heuristik: vor jedem process.terminate()-Aufruf muss ein
    # is_set()-Guard im Source nahe stehen.
    term_positions = [i for i in range(len(src)) if src.startswith("process.terminate()", i)]
    assert len(term_positions) >= 2, "_run_ffmpeg sollte 2 terminate()-Calls haben."
    for tp in term_positions:
        # Vor terminate() muss ein is_set()-Guard im Block stehen,
        # nicht nur cancelled.set() (das ist die Mutation, nicht der Guard).
        prelude = src[max(0, tp - 350):tp]
        assert "is_set()" in prelude, (
            f"process.terminate() ohne is_set()-Guard bei pos {tp} (B-170 race). "
            f"Prelude: {prelude!r}"
        )
