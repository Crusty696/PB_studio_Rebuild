"""B-766: Stiller Supersede-Cancel + blinde Cancel-Fenster im LLM-Block.

Live-Incident 2026-08-06: Ein zweiter Auto-Edit-Klick ("Mit neuen
Pacing-Einstellungen generieren") cancelte den laufenden Lauf via
`attach_worker` -> `prev.cancel()` VOELLIG STILL. Der laufende
`auto_edit_phase3` prueft `should_stop_cb` zwischen Strategist-Start und
Segment-Loop nie — der Cancel wirkte erst nach dem 300s-EDL-Wall-Clock
als raetselhafter "cancel-request bei Segment 0/1417".

Vertraege (Source-Contracts — der volle auto_edit_phase3-Aufbau braucht
Audio/Beats/DB und ist hier bewusst nicht nachgebaut):
1. Nach dem Strategist-Block existiert ein should_stop-Guard.
2. Vor dem EDL-Block existiert ein should_stop-Guard.
3. Der Supersede-Cancel in attach_worker loggt sichtbar (B-766-Marker).
"""
from __future__ import annotations

import inspect

import pytest


def _phase3_source() -> str:
    import services.pacing_service as ps
    return inspect.getsource(ps._auto_edit_phase3_inner)


def test_guard_after_strategist_block():
    src = _phase3_source()
    assert "cancel-request nach LLM-Strategist" in src, (
        "Kein should_stop-Guard nach dem (minutenlang blockierenden) "
        "LLM-Strategist-Block"
    )
    strategist_pos = src.find("generate_pacing_plan")
    guard_pos = src.find("cancel-request nach LLM-Strategist")
    assert 0 < strategist_pos < guard_pos, (
        "Guard muss NACH dem Strategist-Aufruf liegen"
    )


def test_guard_before_edl_block():
    src = _phase3_source()
    assert "cancel-request vor LLM-EDL" in src, (
        "Kein should_stop-Guard vor dem bis zu 300s blockierenden EDL-Call"
    )
    guard_pos = src.find("cancel-request vor LLM-EDL")
    edl_pos = src.find("use_llm_pacing")
    assert 0 < guard_pos < edl_pos, "Guard muss VOR dem EDL-Block liegen"


def test_supersede_cancel_logs_visibly():
    from ui.controllers.schnitt_controller import SchnittController
    src = inspect.getsource(SchnittController.attach_worker)
    assert "B-766" in src and "prev.cancel()" in src, (
        "Supersede-Cancel in attach_worker muss sichtbar loggen — der "
        "stille prev.cancel() liess Laeufe scheinbar grundlos sterben"
    )
    assert src.find("B-766") < src.find("prev.cancel()"), (
        "WARNING muss vor dem cancel stehen"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

