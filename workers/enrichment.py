import logging
import traceback
from typing import List, Dict, Any

import numpy as np
from PySide6.QtCore import QObject, Signal

from database.models import VideoClip, Scene, StructClipTags, StructStyleBucket, StructCompatEdge
from database.session import nullpool_session
from services.analysis_status_service import mark_started, mark_done, mark_error
from services.enrichment.role_classifier import RoleClassifier
from services.enrichment.mood_refiner import MoodRefiner
from services.enrichment.style_clusterer import StyleClusterer
from services.enrichment import compat_graph_builder
from services.vector_db_service import VectorDBService
from workers.base import CancellableMixin, format_user_error

logger = logging.getLogger(__name__)

class StructureEnrichmentWorker(QObject, CancellableMixin):
    """
    Worker coordinating the enrichment of video clips with P3 structure modules.
    
    1. Fetches scenes and SigLIP embeddings.
    2. Classifies roles (cinematic function).
    3. Refines moods using anchors.
    4. Assigns scenes to stylistic buckets.
    5. Builds local compatibility edges.
    6. Persists everything in the database.
    """
    
    started = Signal(int, str)
    progress = Signal(int, str)
    finished = Signal(int, dict)
    error = Signal(int, str)

    STEP_KEY = "structure_enrichment"

    def __init__(self, clip_id: int):
        super().__init__()
        self.clip_id = clip_id
        # We don't initialize services here because they might load heavy models
        # or configs that should only happen inside the run() thread.

    def run(self):
        self.started.emit(self.clip_id, f"Clip {self.clip_id}")
        mark_started("video", self.clip_id, self.STEP_KEY)

        try:
            # Lazy initialization inside the thread
            # VectorDBService is a singleton via __new__
            vector_db = VectorDBService()
            role_classifier = RoleClassifier()
            mood_refiner = MoodRefiner()
            style_clusterer = StyleClusterer()

            with nullpool_session() as session:
                clip = session.query(VideoClip).filter_by(id=self.clip_id).first()
                if not clip:
                    raise ValueError(f"VideoClip {self.clip_id} not found")

                scenes = session.query(Scene).filter_by(video_clip_id=self.clip_id).all()
                if not scenes:
                    logger.info(f"No scenes found for clip {self.clip_id}, skipping enrichment.")
                    mark_done("video", self.clip_id, self.STEP_KEY, {"scenes": 0})
                    self.finished.emit(self.clip_id, {"scenes": 0})
                    return

                # Fetch all embeddings for this clip from VectorDB
                # Embeddings are stored with ID = clip_id * 1_000_000 + scene_index
                embeddings_dict = vector_db.get_embeddings_for_clip(self.clip_id)
                
                if not embeddings_dict:
                     logger.warning(f"No SigLIP embeddings found for clip {self.clip_id}. Skipping enrichment.")
                     mark_done("video", self.clip_id, self.STEP_KEY, {"scenes": 0, "error": "no_embeddings"})
                     self.finished.emit(self.clip_id, {"scenes": 0})
                     return

                # Load Style Buckets for assignment
                buckets_db = session.query(StructStyleBucket).filter_by(active=True).all()
                buckets = []
                for b in buckets_db:
                    # centroid_embedding is stored as JSON list
                    buckets.append({
                        "id": b.id,
                        "centroid": np.array(b.centroid_embedding)
                    })

                valid_scene_ids = []
                scene_embeddings_list = []
                
                total_scenes = len(scenes)
                # Sort scenes by time to match indices in VectorDB
                scenes = sorted(scenes, key=lambda s: s.start_time)

                for i, scene in enumerate(scenes):
                    if self.should_stop():
                        return
                    
                    # Match by composite ID: clip_id * 1_000_000 + i
                    comp_id = self.clip_id * 1_000_000 + i
                    emb = embeddings_dict.get(comp_id)
                    
                    if emb is None:
                        logger.warning(f"Embedding missing for scene {scene.id} (index {i}), skipping scene.")
                        continue
                    
                    # 1. Role classification
                    motion_score = scene.energy or 0.0
                    duration = scene.end_time - scene.start_time
                    tags = scene.ai_tags or []
                    if isinstance(scene.ai_caption, dict):
                        tags.extend(scene.ai_caption.get("tags", []))
                    
                    role, role_conf = role_classifier.classify(motion_score, duration, tags)
                    
                    # 2. Mood refinement
                    ai_mood = scene.ai_mood
                    mood, mood_conf = mood_refiner.refine_mood(emb, ai_mood=ai_mood)
                    
                    # 3. Style assignment
                    style_id = -1
                    style_dist = 0.0
                    if buckets:
                        style_id = style_clusterer.assign_nearest(emb, buckets)
                        # Manually calculate distance to chosen bucket's centroid
                        chosen_bucket = next((b for b in buckets if b["id"] == style_id), None)
                        if chosen_bucket is not None:
                            style_dist = float(np.linalg.norm(emb - chosen_bucket["centroid"]))

                    # 4. Persistence
                    tag_entry = StructClipTags(
                        scene_id=scene.id,
                        role=role,
                        role_confidence=float(role_conf),
                        mood_refined=mood,
                        mood_confidence=float(mood_conf),
                        style_bucket_id=style_id if style_id != -1 else 1, # Fallback to default bucket
                        style_distance=style_dist,
                        enricher_version="1.0.0"
                    )
                    session.merge(tag_entry)
                    
                    valid_scene_ids.append(scene.id)
                    scene_embeddings_list.append(emb)
                    
                    self.progress.emit(int((i + 1) / total_scenes * 80), f"Enriched {i + 1}/{total_scenes} scenes")

                # 5. Compatibility graph building
                if len(scene_embeddings_list) > 1:
                    self.progress.emit(85, "Building local compatibility edges...")
                    embeddings_arr = np.array(scene_embeddings_list)
                    edges = compat_graph_builder.build_edges(valid_scene_ids, embeddings_arr)
                    
                    for edge_data in edges:
                        edge = StructCompatEdge(
                            scene_id_a=edge_data["scene_id_a"],
                            scene_id_b=edge_data["scene_id_b"],
                            cosine_similarity=edge_data["cosine_similarity"],
                            rank_in_a=edge_data["rank_in_a"]
                        )
                        session.merge(edge)

                session.commit()
                
                result_summary = {"scenes": len(valid_scene_ids)}
                mark_done("video", self.clip_id, self.STEP_KEY, result_summary)
                
                self.progress.emit(100, "Structure enrichment complete.")
                self.finished.emit(self.clip_id, result_summary)

        except Exception as e:
            logger.error(f"StructureEnrichmentWorker[{self.clip_id}] crashed: {e}\n{traceback.format_exc()}")
            mark_error("video", self.clip_id, self.STEP_KEY, str(e))
            self._errored = True
            self.error.emit(self.clip_id, format_user_error(e))
