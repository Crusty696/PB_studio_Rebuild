"""B-666: LLM-Pacing-Call darf Auto-Edit nicht unbegrenzt haengen.

Der Pacing-LLM-Call laeuft mit hartem Wall-Clock-Deadline
(``HTTP_OLLAMA_PACING_TIMEOUT_SEC``). Ueberschreitung -> RuntimeError
('pacing_llm_timeout') -> ``generate_pacing_plan`` faellt auf
``PacingPlan.default()`` (degraded, Reason 'pacing_timeout') zurueck.
"""

import time

import pytest


def test_chat_with_deadline_raises_on_hang(monkeypatch):
    """Haengender chat-Call wird nach dem Deadline hart abgebrochen."""
    import services.pacing_strategist as ps

    monkeypatch.setattr(ps, "HTTP_OLLAMA_PACING_TIMEOUT_SEC", 0.2)
    strategist = ps.PacingStrategist()

    class HangingClient:
        def chat(self, **kwargs):
            time.sleep(3.0)  # laenger als der Deadline
            return "{}"

    start = time.monotonic()
    with pytest.raises(RuntimeError) as exc:
        strategist._chat_with_deadline(HangingClient(), "gemma3:4b", "prompt", 128)
    elapsed = time.monotonic() - start

    assert "pacing_llm_timeout" in str(exc.value)
    # Muss beim Deadline zurueckkehren, nicht erst nach dem 3s-Sleep.
    assert elapsed < 2.0, f"Deadline hat nicht gegriffen: {elapsed:.2f}s"


def test_chat_with_deadline_returns_fast_result():
    """Schneller Call liefert das Ergebnis normal (kein False-Timeout)."""
    from services.pacing_strategist import PacingStrategist

    strategist = PacingStrategist()

    class FastClient:
        def chat(self, **kwargs):
            return "OK"

    assert strategist._chat_with_deadline(FastClient(), "m", "p", 128) == "OK"


def test_generate_pacing_plan_labels_timeout_not_unavailable(monkeypatch):
    """Timeout wird als 'pacing_timeout' gelabelt, NICHT als 'ollama_unavailable'."""
    from services.pacing_strategist import PacingStrategist

    strategist = PacingStrategist()

    def _timeout(*args, **kwargs):
        raise RuntimeError("pacing_llm_timeout nach 120s")

    monkeypatch.setattr(strategist, "_generate", _timeout)

    plan = strategist.generate_pacing_plan(
        sections=[{"type": "DROP", "start": 0, "end": 30, "avg_energy": 0.9}],
        bpm=140,
        total_duration=30,
        clip_count=3,
    )

    assert getattr(plan, "degraded", False) is True
    reason = getattr(plan, "degraded_reason", "")
    assert reason.startswith("pacing_timeout:"), reason
    assert "ollama_unavailable" not in reason
