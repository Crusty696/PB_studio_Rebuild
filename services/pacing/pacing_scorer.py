"""T6.3: PacingScorer — Computes a total score between 0.0 and 1.0 by summing 13 weighted terms.
Includes logic for energy match, rhythm sync, memory boost, etc.
"""

import logging
import yaml
import os
import numpy as np

logger = logging.getLogger(__name__)

class PacingScorer:
    def __init__(self, weights_path: str = "config/pacing_weights.yaml"):
        """Initialisiert den Scorer und laedt die Gewichte.
        
        Args:
            weights_path: Pfad zur YAML-Datei mit den Gewichten.
        """
        self.weights = self._load_weights(weights_path)

    def _load_weights(self, path: str) -> dict:
        """Laedt Gewichte aus einer YAML-Datei."""
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    config = yaml.safe_load(f)
                    return config.get("weights", {})
        except Exception as e:
            logger.warning(f"Konnte Gewichte nicht laden: {e}. Nutze Defaults.")
        
        # Fallback-Gewichte (gleiche wie in YAML)
        return {
            "w_energy_match": 0.20,
            "w_role_match": 0.10,
            "w_novelty": 0.05,
            "w_rhythm_sync": 0.15,
            "w_memory_boost": 0.10,
            "w_style_continuity": 0.05,
            "w_color_cohesion": 0.05,
            "w_subject_focus": 0.05,
            "w_clip_stability": 0.05,
            "w_freshness": 0.05,
            "w_vibe_match": 0.05,
            "w_transition_smoothness": 0.05,
            "w_human_presence": 0.05,
        }

    def calculate_score(self, candidate, context, variations_budget, memory_snapshot=None) -> float:
        """Berechnet den Gesamt-Score für einen Kandidaten.
        
        Args:
            candidate: Metadaten-Dict der Szene/des Clips.
            context: Aktueller Pacing-Kontext (Energy, Section, PrevClip, etc).
            variations_budget: Instanz von VariationsBudget.
            memory_snapshot: Optionale KI-Gedaechtnis-Daten.
            
        Returns:
            float: Score zwischen 0.0 und 1.0.
        """
        terms = {}
        
        # 1. w_energy_match: Match visual motion to audio energy
        target_energy = context.get("energy", 0.5)
        motion = candidate.get("motion_score", 0.5)
        terms["w_energy_match"] = 1.0 - abs(motion - target_energy)
        
        # 2. w_role_match: Match to section type
        section_type = context.get("section_type", "TRANSITION")
        # Einfache Heuristik: DROP mag hohe Motion, BREAKDOWN niedrige
        if section_type == "DROP":
            terms["w_role_match"] = motion if motion > 0.6 else 0.2
        elif section_type == "BREAKDOWN":
            terms["w_role_match"] = (1.0 - motion) if motion < 0.4 else 0.2
        else:
            terms["w_role_match"] = 0.5
            
        # 3. w_novelty: Benefit for new clips (not used in this project yet)
        terms["w_novelty"] = 1.0  # Placeholder
        
        # 4. w_rhythm_sync: AUD-101: Beat-Sync logic
        # Erfordert CrossModalMatcher-ähnliche Logik (Distanz zu Beats)
        # Hier vereinfacht: candidate['beat_sync'] falls vorhanden
        terms["w_rhythm_sync"] = candidate.get("beat_sync_score", 0.5)
        
        # 5. w_memory_boost: Bias from AI memory
        memory_bias = context.get("memory_bias", 0.0)
        
        # Integrate boost from learned patterns
        learned_patterns = context.get("learned_patterns", [])
        if learned_patterns:
            for pattern in learned_patterns:
                if pattern.pattern_type == 'context_preference':
                    fp = pattern.context_fingerprint or {}
                    tr = pattern.target_ref or {}
                    
                    # Match context fingerprint (genre, section, bpm)
                    if (fp.get("at_genre") == context.get("genre") and
                        fp.get("at_section_type") == context.get("section_type") and
                        fp.get("at_bpm") == context.get("bpm") and
                        tr.get("scene_id") == candidate.get("id")):
                        
                        # Use the Wilson confidence as a memory boost
                        # If the pattern is highly confident, we trust it more
                        memory_bias = max(memory_bias, pattern.confidence)
        
        terms["w_memory_boost"] = memory_bias
        
        # 6. w_style_continuity: Visual similarity to previous clip
        prev_embedding = context.get("prev_embedding")
        curr_embedding = candidate.get("embedding")
        if prev_embedding is not None and curr_embedding is not None:
            # Cosine Similarity
            norm_p = np.linalg.norm(prev_embedding) + 1e-8
            norm_c = np.linalg.norm(curr_embedding) + 1e-8
            sim = float(np.dot(prev_embedding, curr_embedding) / (norm_p * norm_c))
            terms["w_style_continuity"] = sim
        else:
            terms["w_style_continuity"] = 0.5
            
        # 7-9. Mocks
        terms["w_color_cohesion"] = 0.5
        terms["w_subject_focus"] = 0.5
        terms["w_clip_stability"] = 0.5
        
        # 10. w_freshness: Penalty from budget
        clip_id = candidate.get("video_clip_id", candidate.get("id"))
        penalty = variations_budget.get_penalty(clip_id) if variations_budget else 0.0
        terms["w_freshness"] = 1.0 - penalty
        
        # 11. w_vibe_match: SigLIP / Vibe match score
        terms["w_vibe_match"] = candidate.get("fitness_score", 0.5)
        
        # 12. Mock
        terms["w_transition_smoothness"] = 0.5
        
        # 13. w_human_presence: Match vocal presence to human clips
        vocal_active = context.get("vocal_active", False)
        # Wenn wir wüssten, ob der Clip Menschen enthält (z.B. via Moondream/Tags)
        has_human = candidate.get("has_human", False)
        if vocal_active:
            terms["w_human_presence"] = 1.0 if has_human else 0.2
        else:
            terms["w_human_presence"] = 0.5
            
        # Gesamtsumme berechnen
        total_score = 0.0
        total_weight = 0.0
        
        for name, weight in self.weights.items():
            val = terms.get(name, 0.5)
            total_score += val * weight
            total_weight += weight
            
        if total_weight > 0:
            total_score /= total_weight
            
        return float(np.clip(total_score, 0.0, 1.0))
