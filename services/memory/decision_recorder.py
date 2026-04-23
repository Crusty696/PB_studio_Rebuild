import logging
import time
from datetime import datetime
from sqlalchemy.exc import OperationalError
from database.session import nullpool_session
from database.models import MemDecision

logger = logging.getLogger(__name__)

class DecisionRecorder:
    """
    Service responsible for persisting pacing decisions into the database.
    This provides a 'context-rich' memory of why the agent chose a specific scene.
    """
    def __init__(self, max_retries: int = 3, retry_delay: float = 0.5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def record(self, run_id: int, sequence_idx: int, audio_ctx: dict, scene_id: int, 
               video_ctx: dict, agent_score: float, agent_rationale: dict, 
               enricher_version: str = "1.0.0") -> int:
        """
        Persists a single pacing decision with its full audio/video context snapshot.
        
        Args:
            run_id: ID of the mem_pacing_run.
            sequence_idx: Order of the cut in the run.
            audio_ctx: Dictionary containing audio features at the cut point.
            scene_id: ID of the chosen scene.
            video_ctx: Dictionary containing video features of the chosen scene.
            agent_score: The final score given by the PacingScorer.
            agent_rationale: JSON-serializable dict containing term contributions and alternatives.
            enricher_version: Version of the structure enrichment used.
            
        Returns:
            The ID of the created MemDecision record.
        """
        for attempt in range(self.max_retries):
            try:
                with nullpool_session() as session:
                    decision = MemDecision(
                        run_id=run_id,
                        sequence_idx=sequence_idx,
                        
                        # Audio Context Snapshot (Denormalized for immutability)
                        at_timestamp_sec=audio_ctx.get("timestamp_sec", 0.0),
                        at_beat_idx=audio_ctx.get("beat_idx"),
                        at_structure_segment_id=audio_ctx.get("structure_segment_id"),
                        at_bpm=audio_ctx.get("bpm"),
                        at_energy=audio_ctx.get("energy"),
                        at_section_type=audio_ctx.get("section_type"),
                        at_key=audio_ctx.get("key"),
                        at_key_confidence=audio_ctx.get("key_confidence"),
                        at_key_modulation=audio_ctx.get("key_modulation"),
                        at_harmonic_tension=audio_ctx.get("harmonic_tension"),
                        at_mood_audio=audio_ctx.get("mood_audio"),
                        at_genre=audio_ctx.get("genre"),
                        at_sub_genre=audio_ctx.get("sub_genre"),
                        at_spectral_hash=audio_ctx.get("spectral_hash"),
                        at_groove_template=audio_ctx.get("groove_template"),
                        at_lufs=audio_ctx.get("lufs"),
                        at_enricher_version=enricher_version,
                        
                        # Video Context Snapshot
                        scene_id=scene_id,
                        clip_role=video_ctx.get("role", "unknown"),
                        clip_mood_refined=video_ctx.get("mood_refined", "unknown"),
                        clip_style_bucket_id=video_ctx.get("style_bucket_id", 0),
                        clip_motion_score=video_ctx.get("motion_score"),
                        
                        # Decision Metadata
                        agent_score=agent_score,
                        agent_rationale=agent_rationale,
                        
                        # Initial Verdict is null until user reviews
                        user_verdict=None,
                        user_verdict_at=None,
                        user_rating=None
                    )
                    session.add(decision)
                    session.commit()
                    
                    decision_id = decision.id
                    logger.debug(f"Recorded decision {decision_id} for run {run_id} at sequence {sequence_idx}")
                    return decision_id
                    
            except OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < self.max_retries - 1:
                    wait = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Database locked in DecisionRecorder, retrying in {wait:.2f}s ({attempt+1}/{self.max_retries})...")
                    time.sleep(wait)
                else:
                    logger.error(f"Failed to record decision after {self.max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error in DecisionRecorder: {e}")
                raise
        
        raise RuntimeError("DecisionRecorder failed to persist data after retries.")
