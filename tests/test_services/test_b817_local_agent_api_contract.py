"""Regression fuer B-817: LocalAgentService-Kompatibilitaetsvertrag."""


def test_b817_default_model_and_device_contract() -> None:
    from services.local_agent_service import DEFAULT_MODEL_ID, LocalAgentService

    default_agent = LocalAgentService(use_ollama=False)
    custom_agent = LocalAgentService(
        model_id="test-model",
        device="cpu",
        use_ollama=False,
    )

    assert default_agent.model_id == DEFAULT_MODEL_ID
    assert custom_agent.model_id == "test-model"
    assert custom_agent.device == "cpu"
