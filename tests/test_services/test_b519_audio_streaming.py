import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from services.brain.audio.audio_embedder import ClapAudioEmbedder, WindowEmbedding

def test_b519_audio_streaming_chunked_loads(monkeypatch):
    monkeypatch.setattr("librosa.get_duration", lambda path: 25.0)
    
    loaded_clips = []
    
    def mock_load(path, sr, mono, offset, duration):
        loaded_clips.append((offset, duration))
        # Return dummy window samples
        return np.zeros(int(duration * sr)), sr
        
    monkeypatch.setattr("librosa.load", mock_load)
    
    # Mock model loading and inference
    monkeypatch.setattr(ClapAudioEmbedder, "_ensure_loaded", lambda self: None)
    monkeypatch.setattr(ClapAudioEmbedder, "_embed_audio_window", lambda self, clip, sr: np.ones(512))
    
    # Mock serializer and fixed sections/aggregate
    mock_serializer = MagicMock()
    
    embedder = ClapAudioEmbedder(serializer=mock_serializer)
    embedder._model = MagicMock()
    embedder._processor = MagicMock()
    
    # We must mock _fixed_sections and _aggregate_to_sections to avoid relying on actual logic
    monkeypatch.setattr(embedder, "_fixed_sections", lambda duration: [0.0, 30.0])
    monkeypatch.setattr(embedder, "_aggregate_to_sections", lambda windows, marks, dur: [
        MagicMock(embedding=np.ones(512))
    ])
    
    progress_calls = []
    def progress_cb(pct, msg):
        progress_calls.append((pct, msg))
        
    result = embedder.embed_mix(
        audio_path="test_audio.mp3",
        audio_hash="dummy_hash",
        progress_cb=progress_cb
    )
    
    # Check that librosa.load was called with expected offsets/durations
    assert len(loaded_clips) > 0
    offsets = [c[0] for c in loaded_clips]
    assert offsets[0] == 0.0
    assert offsets[1] == 5.0
    
    # Verify progress_cb was called
    assert len(progress_calls) > 0
    assert progress_calls[0][0] == 0
    
    # Verify result is returned
    assert result is not None


def test_b519_audio_streaming_cancellation(monkeypatch):
    monkeypatch.setattr("librosa.get_duration", lambda path: 30.0)
    monkeypatch.setattr("librosa.load", lambda *args, **kwargs: (np.zeros(480000), 48000))
    monkeypatch.setattr(ClapAudioEmbedder, "_ensure_loaded", lambda self: None)
    monkeypatch.setattr(ClapAudioEmbedder, "_embed_audio_window", lambda self, clip, sr: np.ones(512))
    
    mock_serializer = MagicMock()
    embedder = ClapAudioEmbedder(serializer=mock_serializer)
    embedder._model = MagicMock()
    embedder._processor = MagicMock()
    
    monkeypatch.setattr(embedder, "_fixed_sections", lambda duration: [0.0, 30.0])
    
    # Cancel after 2 windows
    call_count = 0
    def should_stop():
        nonlocal call_count
        call_count += 1
        return call_count > 2
        
    # We expect RuntimeError because the windows list will be empty or incomplete, 
    # resulting in either empty list RuntimeError or early cancel exit
    with pytest.raises(RuntimeError, match="Embedding mix cancelled"):
        embedder.embed_mix(
            audio_path="test_audio.mp3",
            audio_hash="dummy_hash",
            should_stop=should_stop
        )
        
    assert call_count > 0
