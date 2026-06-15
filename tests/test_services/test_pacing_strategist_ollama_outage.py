def test_pacing_strategist_marks_default_plan_as_degraded_on_ollama_outage(monkeypatch):
    from services.pacing_strategist import PacingStrategist

    strategist = PacingStrategist()

    def _ollama_down(*args, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(strategist, "_generate", _ollama_down)

    plan = strategist.generate_pacing_plan(
        sections=[{"type": "DROP", "start": 0, "end": 30, "avg_energy": 0.9}],
        bpm=140,
        total_duration=30,
        clip_count=3,
    )

    assert getattr(plan, "degraded", False) is True
    assert "ollama" in getattr(plan, "degraded_reason", "").lower()



def test_unclosed_json_fence_parses_via_brace_fallback(monkeypatch):
    """E2E 2026-06-15: truncierte Antwort mit OFFENEM ```json-Fence darf NICHT
    crashen (frueher: ValueError 'substring not found' via raw.index). Der
    Brace-Fallback muss das JSON-Objekt trotzdem extrahieren."""
    from services.pacing_strategist import PacingStrategist

    strategist = PacingStrategist()
    # Oeffnender Fence, KEIN schliessender Fence (max_tokens-Abbruch-Simulation).
    monkeypatch.setattr(
        strategist, "_generate",
        lambda *a, **k: '```json\n{"variety_priority": 0.5}',
    )

    plan = strategist.generate_pacing_plan(
        sections=[{"type": "DROP", "start": 0, "end": 30, "avg_energy": 0.9}],
        bpm=140, total_duration=30, clip_count=3,
    )

    assert getattr(plan, "degraded", True) is False
    assert abs(plan.variety_priority - 0.5) < 1e-6


def test_unparseable_response_labeled_not_ollama(monkeypatch):
    """E2E 2026-06-15: Ollama liefert, aber ohne JSON. Das ist ein Parse-Fehler
    und muss als 'unparseable_response' gelabelt werden, NICHT als
    'ollama_unavailable' (irrefuehrende Diagnose)."""
    from services.pacing_strategist import PacingStrategist

    strategist = PacingStrategist()
    monkeypatch.setattr(
        strategist, "_generate",
        lambda *a, **k: "Sorry, ich kann das gerade nicht.",
    )

    plan = strategist.generate_pacing_plan(
        sections=[{"type": "DROP", "start": 0, "end": 30, "avg_energy": 0.9}],
        bpm=140, total_duration=30, clip_count=3,
    )

    assert getattr(plan, "degraded", False) is True
    reason = getattr(plan, "degraded_reason", "")
    assert reason.startswith("unparseable_response"), reason
    assert "ollama_unavailable" not in reason
