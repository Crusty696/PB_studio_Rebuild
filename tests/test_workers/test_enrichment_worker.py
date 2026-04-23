import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from workers.enrichment import StructureEnrichmentWorker
from database.models import Base, Project, Scene, VideoClip, StructClipTags, StructStyleBucket, AnalysisStatus

@pytest.fixture
def test_db():
    """Erzeugt eine frische In-Memory Datenbank für jeden Test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Default Style Bucket anlegen (ID 1)
    bucket = StructStyleBucket(id=1, name="Default", centroid_embedding=[0.0]*1152)
    session.add(bucket)
    session.commit()
    
    yield session
    session.close()

@pytest.fixture
def worker():
    return StructureEnrichmentWorker(clip_id=1)

def test_worker_runs_all_steps(worker, test_db):
    """Verify that all enrichment steps are called in sequence using a real DB session."""
    
    # Setup Data
    project = Project(id=1, name="Test Project", path="C:/test")
    test_db.add(project)
    clip = VideoClip(id=1, project_id=1, file_path="test.mp4")
    test_db.add(clip)
    scene1 = Scene(id=10, video_clip_id=1, start_time=0, end_time=2, energy=0.5, ai_mood="energetic")
    scene2 = Scene(id=11, video_clip_id=1, start_time=2, end_time=4, energy=0.3, ai_mood="calm")
    test_db.add_all([scene1, scene2])
    test_db.commit()
    
    # Mock VectorDBService instance
    mock_vdb_instance = MagicMock()
    # Composite IDs: clip_id * 1_000_000 + index
    mock_embeddings = {
        1_000_000: np.zeros(1152),
        1_000_001: np.zeros(1152)
    }
    mock_vdb_instance.get_embeddings_for_clip.return_value = mock_embeddings
    
    with patch("workers.enrichment.VectorDBService", return_value=mock_vdb_instance), \
         patch("workers.enrichment.nullpool_session", return_value=MagicMock(__enter__=lambda s: test_db, __exit__=lambda s, *a: None)), \
         patch("workers.enrichment.RoleClassifier") as MockRole, \
         patch("workers.enrichment.MoodRefiner") as MockMood, \
         patch("workers.enrichment.StyleClusterer") as MockStyle, \
         patch("workers.enrichment.compat_graph_builder.build_edges") as MockBuildEdges:

        MockRole.return_value.classify.return_value = ("action", 0.9)
        MockMood.return_value.refine_mood.return_value = ("aggressive", 0.8)
        MockStyle.return_value.assign_nearest.return_value = 1
        MockBuildEdges.return_value = [
            {"scene_id_a": 10, "scene_id_b": 11, "cosine_similarity": 0.95, "rank_in_a": 1}
        ]
        
        # Run worker
        worker.run()
        
        # Verifications
        assert MockRole.return_value.classify.call_count == 2
        assert MockMood.return_value.refine_mood.call_count == 2
        
        # Check if data exists in DB
        tags = test_db.query(StructClipTags).all()
        assert len(tags) == 2
        assert tags[0].role == "action"

def test_worker_handles_missing_embeddings(worker, test_db):
    """Ensure worker skips enrichment and finishes if SigLIP embeddings are missing."""
    project = Project(id=1, name="Test Project", path="C:/test")
    test_db.add(project)
    clip = VideoClip(id=1, project_id=1, file_path="test.mp4")
    test_db.add(clip)
    scene = Scene(id=10, video_clip_id=1, start_time=0, end_time=2)
    test_db.add(scene)
    test_db.commit()
    
    mock_vdb_instance = MagicMock()
    mock_vdb_instance.get_embeddings_for_clip.return_value = {} # Empty
    
    with patch("workers.enrichment.VectorDBService", return_value=mock_vdb_instance), \
         patch("workers.enrichment.nullpool_session", return_value=MagicMock(__enter__=lambda s: test_db, __exit__=lambda s, *a: None)), \
         patch("workers.enrichment.mark_done") as mock_mark_done:
        
        worker.run()
        
        # Should call mark_done with error summary
        mock_mark_done.assert_called_once()
        assert mock_mark_done.call_args[0][3]["error"] == "no_embeddings"
