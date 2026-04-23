import logging
import threading
from datetime import datetime
from sqlalchemy.orm import Session
from database import engine, TimelineEntry, VideoClip, Scene, MemDecision, MemPacingRun, MemUserFeedbackEvent, nullpool_session

logger = logging.getLogger(__name__)

class FeedbackService:
    """
    Service for asynchronously persisting user feedback on timeline clips.
    Implements Phase P8 (T8.1) of the Studio Brain Plan.
    """

    @classmethod
    def submit_feedback_async(cls, entry_id: int, event_type: str):
        """
        Starts a background thread to persist user feedback.
        
        Args:
            entry_id: The ID of the TimelineEntry.
            event_type: "accept" or "reject".
        """
        thread = threading.Thread(
            target=cls._persist_feedback,
            args=(entry_id, event_type),
            daemon=True
        )
        thread.start()

    @classmethod
    def _persist_feedback(cls, entry_id: int, event_type: str):
        """
        Internal method to find the decision and save the feedback event.
        """
        try:
            with nullpool_session() as session:
                entry = session.get(TimelineEntry, entry_id)
                if not entry or entry.track != "video":
                    return

                # 1. Find the scene associated with this timeline entry
                # We match by media_id (VideoClip.id) and start time
                scene = session.query(Scene).filter(
                    Scene.video_clip_id == entry.media_id,
                    Scene.start_time >= entry.source_start - 0.1,
                    Scene.start_time <= entry.source_start + 0.1
                ).first()

                if not scene:
                    logger.warning(f"No scene found for TimelineEntry {entry_id}")
                    return

                # 2. Find the latest PacingRun for the project of this entry
                # A project can have multiple audio tracks, each could have a pacing run.
                # We look for runs associated with any audio track of the project.
                from database import AudioTrack
                latest_run = session.query(MemPacingRun).join(
                    AudioTrack, AudioTrack.id == MemPacingRun.audio_track_id
                ).filter(
                    AudioTrack.project_id == entry.project_id
                ).order_by(MemPacingRun.started_at.desc()).first()
                
                # Fallback: if we can't link via project, just take the latest run overall that has this scene
                if not latest_run:
                    latest_run = session.query(MemPacingRun).join(MemDecision).filter(
                        MemDecision.scene_id == scene.id
                    ).order_by(MemPacingRun.started_at.desc()).first()

                if not latest_run:
                    logger.warning(f"No MemPacingRun found for TimelineEntry {entry_id}")
                    return

                # 3. Find the Decision in that run
                decision = session.query(MemDecision).filter(
                    MemDecision.run_id == latest_run.id,
                    MemDecision.scene_id == scene.id
                ).first()

                if not decision:
                    logger.warning(f"No MemDecision found in run {latest_run.id} for scene {scene.id}")
                    # Even if no specific decision is found, we can still record a feedback event for the run
                    decision_id = None
                else:
                    decision_id = decision.id
                    # Update the decision verdict directly as well
                    decision.user_verdict = event_type
                    decision.user_verdict_at = datetime.utcnow()

                # 4. Create the Feedback Event
                event = MemUserFeedbackEvent(
                    decision_id=decision_id,
                    run_id=latest_run.id,
                    event_type=event_type,
                    payload={"entry_id": entry_id, "timestamp": datetime.utcnow().isoformat()},
                    created_at=datetime.utcnow()
                )
                session.add(event)
                session.commit()
                
                logger.info(f"Persisted feedback '{event_type}' for entry {entry_id} (Decision: {decision_id})")

        except Exception as e:
            logger.error(f"Error persisting feedback for entry {entry_id}: {e}", exc_info=True)
