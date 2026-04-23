"""T6.4: 4-stage pacing pipeline integration.
Logic: Refactor PacingAgent to use a 4-stage selection:
1. Filter (Hard Rules): Exclude unanalyzed/deleted scenes.
2. Budget: Exclude scenes with extreme repetition penalty.
3. Score: Run remaining candidates through PacingScorer.
4. Select: Apply WilsonLowerBound logic then pick top-scoring candidate.
"""

import logging
import random
from typing import List, Dict, Any, Optional

from services.pacing.variations_budget import VariationsBudget
from services.pacing.pacing_scorer import PacingScorer
from services.pacing_utils import WilsonLowerBound
from database.models import MemLearnedPattern

logger = logging.getLogger(__name__)

class PacingPipeline:
    def __init__(self, weights_path: str = "config/pacing_weights.yaml"):
        self.budget = VariationsBudget(history_size=20)
        self.scorer = PacingScorer(weights_path)
        self.memory_patterns = []

    def load_memory_patterns(self, session, confidence_threshold: float = 0.5):
        """Loads learned patterns from the database that meet the confidence threshold.
        
        Args:
            session: SQLAlchemy session.
            confidence_threshold: Minimum confidence score (Wilson lower bound) to load a pattern.
        """
        try:
            self.memory_patterns = session.query(MemLearnedPattern).filter(
                MemLearnedPattern.confidence >= confidence_threshold
            ).all()
            logger.info(f"Loaded {len(self.memory_patterns)} memory patterns with confidence >= {confidence_threshold}")
        except Exception as e:
            logger.error(f"Failed to load memory patterns: {e}")
            self.memory_patterns = []

    def select_best_scene(
        self,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any],
        memory_snapshot: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Führt die 4-stufige Auswahlpipeline aus.
        
        Args:
            candidates: Liste von Szenen-Metadaten.
            context: Aktueller Pacing-Kontext.
            memory_snapshot: KI-Gedaechtnis-Daten (legacy or external).
            
        Returns:
            Beste Szene oder None.
        """
        if not candidates:
            return None

        # --- Stage 1: Filter (Hard Rules) ---
        # In diesem Kontext sind candidates bereits vorgefiltert (nicht gelöscht).
        # Wir stellen sicher, dass sie analysiert wurden (motion_score vorhanden).
        filtered = [c for c in candidates if c.get("motion_score") is not None]
        if not filtered:
            logger.warning("Keine analysierten Szenen in den Kandidaten.")
            filtered = candidates # Fallback auf alle
            
        # --- Stage 2: Budget (Repetition Penalty) ---
        # Wir schließen Szenen mit extremer Strafe (> 0.8) aus.
        budget_filtered = []
        for c in filtered:
            clip_id = c.get("video_clip_id", c.get("id"))
            penalty = self.budget.get_penalty(clip_id)
            if penalty < 0.8:  # Harte Grenze für Wiederholung
                budget_filtered.append(c)
        
        if not budget_filtered:
            # Wenn alle bestraft werden, nehmen wir die mit der geringsten Strafe
            logger.info("Alle Szenen im Budget bestraft, nehme beste verfügbare.")
            budget_filtered = sorted(filtered, key=lambda x: self.budget.get_penalty(x.get("video_clip_id", x.get("id"))))[:5]

        # --- Stage 3: Score ---
        scored_candidates = []
        # Pass loaded memory patterns to the scorer via the context or directly
        context_with_memory = context.copy()
        context_with_memory["learned_patterns"] = self.memory_patterns

        for c in budget_filtered:
            score = self.scorer.calculate_score(c, context_with_memory, self.budget, memory_snapshot)
            c_copy = c.copy()
            c_copy["_pipeline_score"] = score
            scored_candidates.append(c_copy)
            
        # --- Stage 4: Select ---
        # Sortieren und den besten wählen
        scored_candidates.sort(key=lambda x: x["_pipeline_score"], reverse=True)
        
        if not scored_candidates:
            return None
            
        best = scored_candidates[0]
        
        # In Budget registrieren
        self.budget.record_usage(best.get("video_clip_id", best.get("id")))
        
        return best
