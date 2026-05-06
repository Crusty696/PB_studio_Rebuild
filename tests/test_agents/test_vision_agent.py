from unittest.mock import MagicMock, patch

from agents.vision_agent import VisionAgent


def test_video_content_question_reads_existing_clip_description():
    agent = VisionAgent()
    fake_registry = MagicMock()
    fake_registry.execute.return_value = {"status": "ok", "message": "Video #1"}

    with patch("services.action_registry.action_registry", fake_registry):
        result = agent.process("Was ist auf Video 1 zu sehen?")

    assert result["action"] == "describe_video_clip"
    assert result["params"] == {"clip_id": 1}
    fake_registry.execute.assert_called_once_with(
        "describe_video_clip",
        {"clip_id": 1},
    )


def test_explicit_video_analysis_still_starts_content_worker():
    agent = VisionAgent()
    fake_registry = MagicMock()
    fake_registry.execute.return_value = {"status": "Task gestartet"}

    with patch("services.action_registry.action_registry", fake_registry):
        result = agent.process("Analysiere Video 1 neu mit KI")

    assert result["action"] == "analyze_video_content"
    assert result["params"] == {"clip_id": 1}
    fake_registry.execute.assert_called_once_with(
        "analyze_video_content",
        {"clip_id": 1},
    )
