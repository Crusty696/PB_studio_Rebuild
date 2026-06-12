import numpy as np
import pytest
import torch
from unittest.mock import MagicMock, patch
from services.brain_v3.video.video_embedder import _l2_normalize, Siglip2VideoEmbedder, SceneSpec
from services.video_analysis_service import generate_embeddings, SceneInfo

def test_l2_normalize_with_nan():
    # Vektor mit NaN darf die Normierung nicht crashen und soll zurueckgegeben werden
    v = np.array([1.0, np.nan, 3.0], dtype=np.float32)
    normed = _l2_normalize(v)
    assert np.isnan(normed[1])
    
    # Valider Vektor wird normalisiert
    v2 = np.array([3.0, 4.0], dtype=np.float32)
    normed2 = _l2_normalize(v2)
    assert np.allclose(normed2, np.array([0.6, 0.8]))

def test_video_embedder_nan_skip():
    # Mock Siglip2VideoEmbedder _embed_in_batches und _sample_frames so, dass ein NaN erzeugt wird
    embedder = object.__new__(Siglip2VideoEmbedder)
    embedder.serializer = MagicMock()
    embedder.serializer.acquire.return_value.__enter__ = MagicMock()
    embedder.serializer.acquire.return_value.__exit__ = MagicMock()
    embedder._ensure_loaded = MagicMock()
    embedder._vision = MagicMock()
    embedder._processor = MagicMock()
    
    # 2 Szenen, eine erzeugt NaN, die andere valide Embeddings
    scenes = [
        SceneSpec(start_time=0.0, end_time=2.0),
        SceneSpec(start_time=2.0, end_time=4.0)
    ]
    
    # Mock cap, cv2
    cap_mock = MagicMock()
    cap_mock.isOpened.return_value = True
    cap_mock.get.side_effect = lambda prop: 10.0 if prop == 5 else 100.0  # CAP_PROP_FPS, CAP_PROP_FRAME_COUNT
    
    with patch('cv2.VideoCapture', return_value=cap_mock), \
         patch.object(Siglip2VideoEmbedder, '_sample_frames', return_value=(scenes, [1, 2])), \
         patch.object(Siglip2VideoEmbedder, '_embed_in_batches', return_value=[
             np.array([1.0, np.nan, 3.0]), # NaN-Embedding
             np.array([3.0, 4.0, 0.0])      # Valides Embedding
         ]):
        res = embedder.embed_clip("dummy.mp4", "dummyhash", scenes)
        
        # Die Szene mit dem NaN-Embedding wurde uebersprungen
        assert len(res.scene_embeddings) == 1
        assert res.scene_embeddings[0].start_time == 2.0
        assert res.scene_embeddings[0].end_time == 4.0
        assert np.allclose(res.scene_embeddings[0].embedding, np.array([0.6, 0.8, 0.0], dtype=np.float32))

def test_video_analyzer_nan_skip():
    # Testet die Batch- und Single-NaN-Filterung in generate_embeddings
    
    # 2 Szenen mit existierenden Keyframes
    scenes = [
        SceneInfo(index=0, start_time=0.0, end_time=1.0, keyframe_path="test_k1.png"),
        SceneInfo(index=1, start_time=1.0, end_time=2.0, keyframe_path="test_k2.png")
    ]
    
    # Mock model and processor
    mock_model = MagicMock()
    
    # 2 Outputs: einer mit NaN, einer ohne
    mock_out = torch.tensor([
        [1.0, float('nan')],
        [3.0, 4.0]
    ])
    mock_model.get_image_features.return_value = mock_out
    mock_model.parameters.return_value = iter([torch.empty(1, dtype=torch.float32)])
    
    mock_processor = MagicMock()
    mock_processor.return_value = {"pixel_values": torch.empty(2, 3, 224, 224)}
    
    # Mock ModelManager instance
    mock_mm_inst = MagicMock()
    mock_mm_inst.device = "cpu"
    
    with patch('pathlib.Path.exists', return_value=True), \
         patch('PIL.Image.open', return_value=MagicMock()), \
         patch('services.model_manager.ModelManager', return_value=mock_mm_inst):
        
        res_scenes = generate_embeddings(scenes, siglip_model_processor=(mock_model, mock_processor))
        
        # Erste Szene hat NaN und bleibt None
        assert res_scenes[0].embedding is None
        # Zweite Szene ist valide und normiert (3/5 = 0.6, 4/5 = 0.8)
        assert res_scenes[1].embedding is not None
        assert np.allclose(res_scenes[1].embedding, np.array([0.6, 0.8], dtype=np.float32))
