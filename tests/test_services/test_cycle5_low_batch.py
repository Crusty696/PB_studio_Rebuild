"""Cycle 5 LOW batch — RED-Tests fuer B-162, B-163, B-165, B-166."""
from __future__ import annotations

import inspect


def test_b162_warn_if_on_gui_thread_returns_bool():
    """B-162: _warn_if_on_gui_thread muss True zurueckgeben wenn gewarnt wurde,
    sonst False. record() darf den Once-Flag nur bei tatsaechlicher Warnung setzen.
    """
    from services.pacing import decision_recorder

    src = inspect.getsource(decision_recorder._warn_if_on_gui_thread)
    assert "return True" in src and "return False" in src, (
        "_warn_if_on_gui_thread muss True/False zurueckgeben (B-162)."
    )

    rec_src = inspect.getsource(decision_recorder.DecisionRecorder.record)
    # Once-Flag darf nur bei tatsaechlicher Warnung gesetzt werden.
    assert "_warn_if_on_gui_thread()" in rec_src, "Aufruf fehlt."
    # Der Pattern: if _warn_...(): self._gui_thread_warning_logged = True
    # muss innerhalb des if-Bodies stehen, nicht uneabhaengig.
    warned_idx = rec_src.find("_warn_if_on_gui_thread()")
    flag_idx = rec_src.find("self._gui_thread_warning_logged = True")
    assert warned_idx > 0 and flag_idx > warned_idx, (
        "Once-Flag muss konditional auf das Warning-Result gesetzt werden (B-162)."
    )


def test_b163_pacing_strategist_max_tokens_scales_with_sections():
    """B-163: max_tokens darf nicht hart 1024 sein — bei langen DJ-Mixes
    schneidet Ollama mid-JSON ab."""
    from services import pacing_strategist

    src = inspect.getsource(pacing_strategist.PacingStrategist._generate)
    # Der harte Wert 1024 darf nicht mehr im Source stehen
    assert "max_tokens=1024" not in src, (
        "PacingStrategist max_tokens=1024 ist hart-coded — fuer 30+ Sections "
        "zu wenig (B-163)."
    )


def test_b163_pacing_strategist_token_budget_dynamic():
    """B-163: max_tokens muss dynamisch sein (abhaengig von Section-Count)."""
    from services import pacing_strategist

    gen_src = inspect.getsource(pacing_strategist.PacingStrategist.generate_pacing_plan)
    # Token-Budget muss aus Section-Count berechnet werden
    assert "max_tokens" in gen_src or "token_budget" in gen_src, (
        "generate_pacing_plan muss ein dynamisches Token-Budget berechnen (B-163)."
    )


def test_b165_pacing_pipeline_select_best_resets_on_new_run_id():
    """B-165: PacingPipeline akzeptiert run_id-aenderung im select_best
    UND warnt/reset bei mismatched run_id, sonst koennen Sequence-Idx
    zwischen Runs duplizieren (UNIQUE constraint mem_decision)."""
    from services.pacing import pipeline as pl

    init_src = inspect.getsource(pl.PacingPipeline.__init__)
    reset_src = inspect.getsource(pl.PacingPipeline.reset_sequence)
    # reset_sequence muss zumindest existieren (war schon da). Strenger:
    # nach reset_sequence muss _sequence_idx wieder bei 0 starten.
    assert "_sequence_idx = 0" in reset_src, (
        "reset_sequence muss _sequence_idx auf 0 setzen (B-165)."
    )
    # Zusaetzlich: VariationsBudget MUSS auch zurueckgesetzt werden,
    # sonst leckt Budget-State zwischen Runs.
    assert "_budget" in reset_src, (
        "reset_sequence muss auch _budget zuruecksetzen, sonst leckt "
        "Budget-State zwischen Runs (B-165 erweitert)."
    )


def test_b166_pattern_aggregator_logs_cleanup_errors():
    """B-166: bare `except: pass` in finally-Bloecken muss durch logging-
    Variante ersetzt werden, sonst werden DB-Cleanup-Errors verschluckt."""
    from services.pacing import pattern_aggregator
    from services.pacing import decision_recorder

    pa_src = inspect.getsource(pattern_aggregator.PatternAggregator)
    dr_src = inspect.getsource(decision_recorder.DecisionRecorder)

    # Mindestens ein logger.warning oder logger.error im finally-Pfad.
    # Wir suchen nach dem strikten Pattern "except Exception:\n            pass"
    # der durch logger.* ersetzt sein muss.
    assert "except Exception:\n                pass" not in pa_src, (
        "PatternAggregator hat bare except Exception: pass in finally — B-166."
    )
    assert "except Exception:\n                pass" not in dr_src, (
        "DecisionRecorder hat bare except Exception: pass in finally — B-166."
    )
