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
