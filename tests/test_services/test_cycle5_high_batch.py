"""Cycle 5 HIGH batch — RED-Tests fuer B-157, B-159, B-164.

Source-inspection-Tests (kein DB/GPU). Asserten strukturelle
Eigenschaften der gefixten Production-Funktionen, sodass Code-Drift
sofort fehlschlaegt.
"""
from __future__ import annotations

import inspect


def test_b157_autoeditworker_propagates_cancel_to_pipeline():
    """B-157: AutoEditWorker.run() muss should_stop_cb an auto_edit_phase3 reichen.

    Erbt CancellableMixin → muss bei Cancel-Request den Pipeline-Lauf
    abbrechen, sonst laeuft auto_edit_phase3 (60+ Cuts × Cross-Modal-Match)
    voll durch.
    """
    from workers import edit as edit_mod

    src = inspect.getsource(edit_mod.AutoEditWorker.run)
    assert "should_stop" in src, (
        "AutoEditWorker.run() muss should_stop / should_stop_cb an "
        "auto_edit_phase3 reichen — kein Hinweis auf cancel-Propagation gefunden."
    )


def test_b157_auto_edit_phase3_accepts_should_stop_cb():
    """B-157: auto_edit_phase3 muss eine should_stop_cb akzeptieren und
    im Segment-Loop pruefen."""
    from services import pacing_service

    sig = inspect.signature(pacing_service.auto_edit_phase3)
    assert "should_stop_cb" in sig.parameters, (
        "auto_edit_phase3 muss should_stop_cb-kwarg unterstuetzen, sonst "
        "kann der Worker den Lauf nicht abbrechen."
    )

    src = inspect.getsource(pacing_service.auto_edit_phase3)
    assert "should_stop_cb" in src, "Source ohne Verwendung der Cancel-Callback."
    # Cancel-Check sollte im Segment-Loop sitzen, nicht nur am Anfang.
    # Heuristik: der Check muss NACH dem 'for i in range(len(cut_beats) - 1)' stehen.
    seg_loop_idx = src.find("for i in range(len(cut_beats)")
    cb_idx = src.find("should_stop_cb", seg_loop_idx if seg_loop_idx >= 0 else 0)
    assert seg_loop_idx > 0 and cb_idx > seg_loop_idx, (
        "should_stop_cb-Pruefung fehlt im Segment-Erzeugungs-Loop."
    )


def test_b159_scorer_historical_accept_rate_uses_scene_id():
    """B-159: scorer.historical_accept_rate muss clip.scene_id passen, nicht clip.clip_id.

    Der PatternAggregator schreibt patterns gekeyed auf scene_id (mem_decision.scene_id);
    wenn der Scorer per clip_id query'd, matcht der Lookup nie und das gesamte
    Lern-Loop ist tot (w_memory faellt immer auf den 0.5-Default).
    """
    from services.pacing import scorer as scorer_mod

    src = inspect.getsource(scorer_mod.historical_accept_rate)
    assert "clip.scene_id" in src, (
        "historical_accept_rate muss clip.scene_id durchreichen — sonst "
        "matcht der Memory-Lookup nie (B-159)."
    )
    assert "clip.clip_id" not in src, (
        "historical_accept_rate darf NICHT clip.clip_id verwenden — "
        "PatternAggregator keyed auf scene_id (B-159)."
    )


def test_b164_stem_cache_max_reduced_for_long_djmix():
    """B-164: _STEM_CACHE_MAX muss <= 2 sein, sonst RAM-OOM bei 60-min DJ-Mixes.

    Bei 22050 Hz mono float32 × 60 min × 4 Stems = ~1.27 GB pro audio_id.
    5 cached audio_ids = ~6.35 GB → OOM-Risiko.
    """
    from services import pacing_beat_grid

    assert hasattr(pacing_beat_grid, "_STEM_CACHE_MAX"), "Konstante fehlt."
    assert pacing_beat_grid._STEM_CACHE_MAX <= 2, (
        f"_STEM_CACHE_MAX={pacing_beat_grid._STEM_CACHE_MAX} ist zu hoch — "
        f"bei 60-min DJ-Mix (~1.27 GB pro audio_id) drohen >5 GB RAM (B-164). "
        f"Reduziere auf <= 2."
    )
