import logging
from datetime import datetime
from sqlalchemy import func, case
from database.session import nullpool_session
from database.models import MemDecision, MemLearnedPattern, MemUserFeedbackEvent, MemPacingRun
from services.pacing_utils import WilsonLowerBound

logger = logging.getLogger(__name__)

class PatternAggregator:
    """
    Aggregates user feedback from mem_user_feedback_event and mem_decision 
    into learned patterns in mem_learned_pattern.
    """
    
    def __init__(self):
        pass

    def run_aggregation_cycle(self):
        """
        Executes a full aggregation cycle:
        1. Syncs user_verdict from feedback events to decisions.
        2. Aggregates decisions with feedback into patterns.
        3. Calculates confidence scores using Wilson Lower Bound.
        """
        logger.info("Starting memory aggregation cycle...")
        
        try:
            with nullpool_session() as session:
                # Step 1: Sync feedback events to decisions
                # Find events that haven't been applied to decisions yet
                # For simplicity in this implementation, we scan and update
                events_to_sync = session.query(MemUserFeedbackEvent).filter(
                    MemUserFeedbackEvent.decision_id != None
                ).all()
                
                for event in events_to_sync:
                    decision = session.get(MemDecision, event.decision_id)
                    if decision and decision.user_verdict != event.event_type:
                        decision.user_verdict = event.event_type
                        decision.user_verdict_at = event.created_at
                
                session.commit()
                
                # Step 2: Aggregate by Context Fingerprint
                # Fingerprint: (at_genre, at_section_type, at_bpm)
                # We group by these fields + target (scene_id)
                
                # Logic for Run-level rating:
                # "Run-Rating ohne Einzel-Ratings: Dämpfungs-Gewicht 0.3x auf alle Decisions dieses Runs."
                # This is tricky with raw SQL grouping. We'll handle it by calculating effective weights.
                
                # Subquery to get run ratings
                run_ratings = session.query(
                    MemPacingRun.id,
                    MemPacingRun.user_rating
                ).filter(MemPacingRun.user_rating != None).subquery()
                
                # Main aggregation query
                # We calculate effective accept/reject counts
                # If a decision has an explicit verdict, weight is 1.0
                # If it doesn't, but the run has a rating >= 4 (good), it counts as 0.3 accept
                # If it doesn't, but the run has a rating <= 2 (bad), it counts as 0.3 reject
                
                decisions = session.query(MemDecision).all()
                
                patterns_map = {} # (fingerprint_hash) -> {accepts: float, rejects: float}
                
                for d in decisions:
                    weight = 1.0
                    is_accept = False
                    is_reject = False
                    
                    if d.user_verdict == 'accept':
                        is_accept = True
                    elif d.user_verdict == 'reject':
                        is_reject = True
                    elif d.user_verdict is None:
                        # Check run rating
                        run = session.get(MemPacingRun, d.run_id)
                        if run and run.user_rating is not None:
                            weight = 0.3
                            if run.user_rating >= 4:
                                is_accept = True
                            elif run.user_rating <= 2:
                                is_reject = True
                    
                    if not (is_accept or is_reject):
                        continue
                        
                    # Create fingerprint key
                    # Using exact BPM for now as per spec
                    fingerprint_key = (d.at_genre, d.at_section_type, d.at_bpm, d.scene_id)
                    
                    if fingerprint_key not in patterns_map:
                        patterns_map[fingerprint_key] = {'accepts': 0.0, 'rejects': 0.0}
                    
                    if is_accept:
                        patterns_map[fingerprint_key]['accepts'] += weight
                    else:
                        patterns_map[fingerprint_key]['rejects'] += weight
                
                # Step 3: Update MemLearnedPattern
                for (genre, section, bpm, scene_id), stats in patterns_map.items():
                    accepts = stats['accepts']
                    rejects = stats['rejects']
                    total = accepts + rejects
                    
                    if total == 0:
                        continue
                        
                    # Calculate Wilson Score
                    # The helper expects ints, so we round for the confidence calculation
                    # but keep floats for the stats if we wanted to (though DB expects Int)
                    # We'll round for DB storage as requested by schema
                    stat_accept = int(round(accepts))
                    stat_reject = int(round(rejects))
                    stat_total = stat_accept + stat_reject
                    
                    confidence = WilsonLowerBound.calculate(stat_accept, stat_total)
                    
                    fingerprint = {
                        "at_genre": genre,
                        "at_section_type": section,
                        "at_bpm": bpm
                    }
                    target = {"scene_id": scene_id}
                    
                    # Look for existing pattern
                    # Note: SQLite JSON extraction might be needed for precise matching if we had many patterns
                    # For now, we'll iterate and find or just use a more efficient query if possible.
                    
                    # Simplified matching for this implementation
                    pattern = session.query(MemLearnedPattern).filter(
                        MemLearnedPattern.pattern_type == 'context_preference'
                    ).all()
                    
                    existing = None
                    for p in pattern:
                        if (p.context_fingerprint == fingerprint and 
                            p.target_ref == target):
                            existing = p
                            break
                    
                    if existing:
                        existing.stat_accept_count = stat_accept
                        existing.stat_reject_count = stat_reject
                        existing.stat_sample_size = stat_total
                        existing.confidence = confidence
                        existing.last_updated = datetime.utcnow()
                    else:
                        new_pattern = MemLearnedPattern(
                            pattern_type='context_preference',
                            context_fingerprint=fingerprint,
                            target_ref=target,
                            stat_accept_count=stat_accept,
                            stat_reject_count=stat_reject,
                            stat_sample_size=stat_total,
                            confidence=confidence,
                            last_updated=datetime.utcnow()
                        )
                        session.add(new_pattern)
                
                session.commit()
                logger.info(f"Aggregation cycle complete. Updated {len(patterns_map)} patterns.")
                
        except Exception as e:
            logger.error(f"Error in PatternAggregator aggregation cycle: {e}")
            raise
