"""Unit tests for OllamaPacingService and direct EDL reasoning."""

import json
from unittest.mock import MagicMock, patch
import pytest

from services.pacing.ollama_pacing import OllamaPacingService
from services.pacing_beat_grid import AdvancedPacingSettings


class TestOllamaPacing:

    @patch("services.pacing.ollama_pacing.get_ollama_client")
    @patch("services.pacing.ollama_pacing.get_ollama_settings")
    def test_ollama_pacing_service_availability(self, mock_settings, mock_get_client):
        # Setup settings enabled
        mock_settings.return_value = {"enabled": True, "url": "http://localhost:11434"}
        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        mock_get_client.return_value = mock_client

        service = OllamaPacingService()
        assert service.is_available() is True

        # Setup settings disabled
        mock_settings.return_value = {"enabled": False}
        service = OllamaPacingService()
        assert service.is_available() is False

    @patch("services.pacing.ollama_pacing.Session")
    @patch("services.pacing.ollama_pacing.get_ollama_client")
    @patch("services.pacing.ollama_pacing.get_ollama_settings")
    def test_generate_edl_success(self, mock_settings, mock_get_client, mock_session):
        mock_settings.return_value = {"enabled": True, "url": "http://localhost:11434"}
        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        
        # Valid Mock EDL response
        valid_response = """
        {
          "edl": [
            {"start": 0.0, "end": 4.5, "video_id": 1, "scene_id": 10, "transition": "crossfade"},
            {"start": 4.5, "end": 10.0, "video_id": 2, "scene_id": 20, "transition": "hard_cut"}
          ]
        }
        """
        mock_client.chat.return_value = valid_response
        mock_get_client.return_value = mock_client

        # Mock DB Models and query
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        
        mock_track = MagicMock()
        mock_track.duration = 10.0
        mock_track.bpm = 128.0
        
        mock_seg = MagicMock()
        mock_seg.label = "INTRO"
        mock_seg.start_time = 0.0
        mock_seg.end_time = 10.0
        mock_seg.energy = 0.4
        mock_track.structure_segments = [mock_seg]
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_track

        mock_clip1 = MagicMock()
        mock_clip1.id = 1
        mock_clip1.file_path = "test1.mp4"
        mock_clip1.duration = 5.0
        mock_scene1 = MagicMock()
        mock_scene1.id = 10
        mock_scene1.start_time = 0.0
        mock_scene1.end_time = 5.0
        mock_scene1.ai_mood = "calm"
        mock_scene1.ai_tags = ["ambient"]
        mock_clip1.scenes = [mock_scene1]

        mock_clip2 = MagicMock()
        mock_clip2.id = 2
        mock_clip2.file_path = "test2.mp4"
        mock_clip2.duration = 5.0
        mock_scene2 = MagicMock()
        mock_scene2.id = 20
        mock_scene2.start_time = 0.0
        mock_scene2.end_time = 5.0
        mock_scene2.ai_mood = "energetic"
        mock_scene2.ai_tags = ["laser"]
        mock_clip2.scenes = [mock_scene2]

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_clip1, mock_clip2]

        service = OllamaPacingService()
        result = service.generate_edl(audio_id=1, video_clip_ids=[1, 2])

        assert result is not None
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["video_id"] == 1
        assert result[0]["scene_id"] == 10
        assert result[1]["end"] == 10.0
        assert result[1]["video_id"] == 2
        assert result[1]["scene_id"] == 20

    @patch("services.pacing.ollama_pacing.Session")
    @patch("services.pacing.ollama_pacing.get_ollama_client")
    @patch("services.pacing.ollama_pacing.get_ollama_settings")
    def test_generate_edl_unparseable_fallback(self, mock_settings, mock_get_client, mock_session):
        mock_settings.return_value = {"enabled": True, "url": "http://localhost:11434"}
        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        # Return invalid JSON
        mock_client.chat.return_value = "This is not JSON at all."
        mock_get_client.return_value = mock_client

        # Mock DB Query success
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_track = MagicMock()
        mock_track.duration = 10.0
        mock_track.bpm = 128.0
        mock_seg = MagicMock()
        mock_seg.label = "INTRO"
        mock_seg.start_time = 0.0
        mock_seg.end_time = 10.0
        mock_seg.energy = 0.4
        mock_track.structure_segments = [mock_seg]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_track
        mock_db.query.return_value.filter.return_value.all.return_value = []

        service = OllamaPacingService()
        result = service.generate_edl(audio_id=1, video_clip_ids=[1, 2])
        # Returns None to trigger fallback to legacy pacing
        assert result is None
