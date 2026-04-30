from __future__ import annotations

from services.brain_v2.reasoner import BrainReasoner


class FakeOllamaClient:
    def __init__(self, response: str = "", available: bool = True, model: str | None = "gemma3:4b"):
        self.response = response
        self.available = available
        self.model = model

    def is_available(self) -> bool:
        return self.available

    def get_best_available_model(self) -> str | None:
        return self.model

    def chat(self, **kwargs) -> str:
        return self.response


def test_explain_clip_match_parses_valid_ollama_json() -> None:
    client = FakeOllamaClient(
        '{"summary":"fits drop","fit_reasons":["high motion"],"risks":["repeat"],"suggested_feedback_tags":["fits"]}'
    )
    result = BrainReasoner(ollama_client_factory=lambda _url=None: client).explain_clip_match(
        audio_context={"section": "DROP", "energy": 0.9},
        clip_context={"role": "hero", "motion": 0.8},
        candidates=[],
    )
    assert result.used_ollama is True
    assert result.summary == "fits drop"
    assert result.fit_reasons == ["high motion"]
    assert result.suggested_feedback_tags == ["fits"]


def test_explain_clip_match_falls_back_when_ollama_unavailable() -> None:
    client = FakeOllamaClient(available=False)
    result = BrainReasoner(ollama_client_factory=lambda _url=None: client).explain_clip_match(
        audio_context={"section": "BREAKDOWN", "energy": 0.2},
        clip_context={"role": "ambient", "motion": 0.1},
        candidates=[],
    )
    assert result.used_ollama is False
    assert "BREAKDOWN" in result.summary
    assert result.fit_reasons


def test_explain_clip_match_falls_back_on_invalid_json() -> None:
    client = FakeOllamaClient("not json")
    result = BrainReasoner(ollama_client_factory=lambda _url=None: client).explain_clip_match(
        audio_context={"section": "DROP"},
        clip_context={"role": "hero"},
        candidates=[],
    )
    assert result.used_ollama is False
    assert result.error is not None
