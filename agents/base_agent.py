"""
Basisklasse für alle spezialisierten Agenten im Multi-Agenten-System.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstrakte Basisklasse für PB Studio Agenten.

    Jeder Agent hat:
    - einen Namen (für Logging/Routing)
    - eine Domäne (audio, vision, editor, orchestrator)
    - optionale Modell-Anforderungen (model_id)
    - eine process()-Methode

    P2-FIX: Class-Variablen (name, domain, model_id) werden von Subklassen
    überschrieben. Dies ist das korrekte Pattern für diese Anwendung, da
    jede Agent-Klasse nur einmal instanziiert wird.
    """

    name: str = "base"
    domain: str = "generic"
    model_id: str | None = None  # Modell-ID falls dieser Agent ein eigenes Modell braucht

    def __init__(self):
        pass

    @abstractmethod
    def can_handle(self, user_text: str) -> float:
        """Gibt einen Konfidenz-Score (0.0 - 1.0) zurück, wie gut dieser Agent die Anfrage bearbeiten kann.

        Returns:
            0.0 = Kann nicht bearbeiten
            1.0 = Perfekt geeignet
        """
        ...

    @abstractmethod
    def process(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Verarbeitet die Benutzeranfrage.

        Args:
            user_text: Die Eingabe des Benutzers.
            context: Optionaler Kontext (z.B. aktuelle Projekt-IDs, importierte Dateien).

        Returns:
            Ergebnis-Dict mit mindestens 'action', 'result', 'message', 'error'.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' domain='{self.domain}'>"
