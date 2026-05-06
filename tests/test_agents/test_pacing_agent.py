from unittest.mock import MagicMock, patch

from agents.pacing_agent import PacingAgent


def test_cross_modal_drop_query_uses_match_clips_tool():
    agent = PacingAgent()
    fake_registry = MagicMock()
    fake_registry.execute.return_value = {"status": "ok", "message": "matches"}

    with patch("services.action_registry.action_registry", fake_registry):
        result = agent.process("Welche Clips passen zum Drop von Track 1?")

    assert result["action"] == "match_clips_to_segment"
    assert result["params"] == {
        "track_id": 1,
        "segment_label": "DROP",
        "top_n": 5,
        "max_segments": 10,
    }
    fake_registry.execute.assert_called_once_with(
        "match_clips_to_segment",
        result["params"],
    )
