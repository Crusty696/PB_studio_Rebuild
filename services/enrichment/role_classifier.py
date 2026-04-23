import yaml
import os
from typing import List, Tuple, Dict, Any

class RoleClassifier:
    """
    Classifies video scenes into cinematic roles based on motion, duration, and tags.
    Rules are loaded from a YAML configuration file.
    """
    def __init__(self, config_path: str = "config/enrichment_rules.yaml"):
        self.config_path = config_path
        self.rules: Dict[str, Any] = {}
        self.default_role: str = "filler"
        self.confidence_threshold: float = 0.5
        self.reload()

    def reload(self) -> None:
        """Loads or reloads the configuration from the YAML file."""
        if not os.path.exists(self.config_path):
            # Fallback if config is missing during tests or init
            self.rules = {}
            return

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)
            self.rules = config.get("role_definitions", {})
            self.default_role = config.get("default_role", "filler")
            self.confidence_threshold = config.get("confidence_threshold", 0.5)

    def classify(self, motion_score: float, duration: float, tags: List[str]) -> Tuple[str, float]:
        """
        Assigns a role to a scene based on the rules.
        Returns (role_name, confidence).
        """
        best_role = self.default_role
        max_confidence = 0.0
        
        # Tags to set for faster lookup
        tag_set = set(tags)

        for role_name, definition in self.rules.items():
            conditions = definition.get("conditions", {})
            confidence_base = definition.get("confidence_base", 0.0)
            
            match = True
            
            # Check motion_min
            if "motion_min" in conditions and motion_score < conditions["motion_min"]:
                match = False
            
            # Check motion_max
            if match and "motion_max" in conditions and motion_score > conditions["motion_max"]:
                match = False
                
            # Check duration_min
            if match and "duration_min" in conditions and duration < conditions["duration_min"]:
                match = False
                
            # Check duration_max
            if match and "duration_max" in conditions and duration > conditions["duration_max"]:
                match = False
                
            # Check tags_any (at least one tag must match)
            if match and "tags_any" in conditions:
                required_tags = set(conditions["tags_any"])
                if not (tag_set & required_tags):
                    match = False
            
            # If all conditions for this role match
            if match:
                # In this simple implementation, the first matching role with highest confidence wins.
                # Since we iterate through the rules, we keep the one with the highest confidence.
                if confidence_base > max_confidence:
                    max_confidence = confidence_base
                    best_role = role_name

        if max_confidence < self.confidence_threshold:
            # If no rule matched or confidence is too low, return default
            return self.default_role, 1.0
            
        return best_role, max_confidence
