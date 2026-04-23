"""T6.1: VariationsBudget — Tracks used clips to prevent repetition.
Applies exponential penalties for recently used clips.
"""

import math
from collections import deque

class VariationsBudget:
    def __init__(self, history_size: int = 20):
        """Initialisiert das Budget mit einer Historie der letzten N Clips.
        
        Args:
            history_size: Anzahl der zuletzt verwendeten Clips, die getrackt werden.
        """
        self.history = deque(maxlen=history_size)
        self.history_size = history_size

    def record_usage(self, clip_id: int):
        """Registriert die Verwendung eines Clips.
        
        Args:
            clip_id: Die ID des verwendeten Clips.
        """
        self.history.append(clip_id)

    def get_penalty(self, clip_id: int) -> float:
        """Berechnet die Strafe für einen Clip basierend auf seiner letzten Verwendung.
        
        Die Strafe ist 1.0 für den zuletzt verwendeten Clip und sinkt
        exponentiell, je länger die Verwendung zurückliegt.
        
        Strafe = base_penalty * (decay_rate ^ distance)
        
        Args:
            clip_id: Die ID des zu prüfenden Clips.
            
        Returns:
            float: Strafe zwischen 0.0 (keine Strafe) und 1.0 (maximale Strafe).
        """
        # Suche den Clip in der Historie (von hinten nach vorne)
        try:
            # find index from the right (most recent)
            # deque doesn't have rindex, so we convert to list and reverse or iterate
            history_list = list(self.history)
            idx = -1
            for i in range(len(history_list) - 1, -1, -1):
                if history_list[i] == clip_id:
                    idx = i
                    break
            
            if idx == -1:
                return 0.0
                
            # Distanz vom Ende (0 = gerade eben verwendet)
            distance = len(history_list) - 1 - idx
            
            # Exponentielle Strafe
            # Bei distance=0 -> penalty=1.0
            # Bei distance=5 -> penalty=0.5 (wenn wir 0.5^(distance/5) nehmen)
            # Wir nehmen eine steile Kurve: 0.5 ^ (distance / 2)
            penalty = math.pow(0.5, distance / 2.0)
            
            return min(1.0, max(0.0, penalty))
            
        except Exception:
            return 0.0

    def clear(self):
        """Setzt die Historie zurück."""
        self.history.clear()
