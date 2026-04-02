"""
Konversationsgedächtnis — AP-5 (AUD-12).

Sliding-Window Chat-History fuer Multi-Turn-Dialoge mit dem lokalen LLM.

Features:
- In-Memory-Speicher pro Session (kein DB-Overhead für transiente Dialoge)
- Sliding Window: Behaelt nur die letzten N Turns (verhindert Kontext-Overflow)
- Session-Management: Mehrere unabhängige Sessions (z.B. Tab 1 vs Tab 2)
- Ollama-kompatibles Format: {"role": "user/assistant/system", "content": "..."}
- Zusammenfassung älterer Turns (Kompression statt hartem Abschneiden)

VRAM-Bewusstsein: Groessere History -> laengerer Kontext -> mehr VRAM/CPU.
Max-Tokens-Warnung ab 20+ Turns aktiviert.
"""

from __future__ import annotations

import logging
import threading
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Globale Limits (geerbt von GTX 1060 / 6GB-Constraint)
MAX_TURNS_DEFAULT = 8           # 8 Turns = 16 Messages (User + Assistant)
MAX_TURNS_HARD_LIMIT = 20       # Absolutes Maximum — darüber wird gewarnt
SUMMARY_TRIGGER_TURNS = 12      # Ab hier wird eine Zusammenfassung erstellt

# Separater Singleton-Manager für alle Sessions
_manager_instance: ConversationMemoryManager | None = None
_manager_lock = threading.Lock()


class Turn(NamedTuple):
    """Ein Dialog-Turn: User-Frage + Assistent-Antwort."""
    user: str
    assistant: str


class ConversationMemory:
    """In-Memory Sliding-Window Konversationsgedächtnis für eine Session.

    Thread-safe. Alle Methoden können aus UI-Thread und Worker-Threads aufgerufen werden.

    Verwendung:
        mem = ConversationMemory(session_id="main", max_turns=8)
        messages = mem.get_messages(system_prompt="Du bist...")
        # nach LLM-Antwort:
        mem.add_turn("Was ist BPM?", "BPM steht für Beats per Minute...")
    """

    def __init__(self, session_id: str = "default", max_turns: int = MAX_TURNS_DEFAULT):
        self.session_id = session_id
        self.max_turns = min(max_turns, MAX_TURNS_HARD_LIMIT)
        self._turns: list[Turn] = []
        self._lock = threading.Lock()
        self._summary: str | None = None  # Komprimierte Zusammenfassung älterer Turns

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        """Fügt einen neuen Gesprächsschritt hinzu.

        Wenn das Window voll ist, wird der älteste Turn entfernt.
        Ab SUMMARY_TRIGGER_TURNS wird eine Komprimierung ausgelöst.
        """
        with self._lock:
            self._turns.append(Turn(user=user_text, assistant=assistant_text))

            # Sliding Window: Älteste Turns abschneiden
            if len(self._turns) > self.max_turns:
                excess = len(self._turns) - self.max_turns
                dropped = self._turns[:excess]
                self._turns = self._turns[excess:]
                logger.debug(
                    "ConversationMemory[%s]: %d alte Turn(s) aus Window entfernt.",
                    self.session_id, excess,
                )
                # Zusammenfassung der entfernten Turns erstellen (1 Satz pro Turn)
                if dropped:
                    summaries = [
                        f"User fragte: '{t.user[:60]}' → Antwort: '{t.assistant[:80]}'"
                        for t in dropped
                    ]
                    new_summary = " | ".join(summaries)
                    if self._summary:
                        self._summary = self._summary + " | " + new_summary
                    else:
                        self._summary = new_summary

            if len(self._turns) >= SUMMARY_TRIGGER_TURNS:
                logger.warning(
                    "ConversationMemory[%s]: %d Turns — Kontext wird gross (VRAM-Warnung).",
                    self.session_id, len(self._turns),
                )

    def get_messages(self, system_prompt: str) -> list[dict[str, str]]:
        """Gibt die vollständige Message-Liste für Ollama zurück.

        Format: [{"role": "system/user/assistant", "content": "..."}]
        Ältere Turns werden als Zusammenfassung im System-Prompt eingefügt.
        """
        with self._lock:
            messages: list[dict[str, str]] = []

            # System-Prompt (mit optionaler History-Zusammenfassung)
            full_system = system_prompt
            if self._summary:
                full_system += (
                    f"\n\nFRÜHERE GESPRÄCHSHISTORIE (Zusammenfassung):\n{self._summary}"
                )
            messages.append({"role": "system", "content": full_system})

            # Aktuelle Turns als User/Assistant-Messages
            for turn in self._turns:
                messages.append({"role": "user", "content": turn.user})
                messages.append({"role": "assistant", "content": turn.assistant})

            return messages

    def get_last_n_turns(self, n: int = 3) -> list[Turn]:
        """Gibt die letzten N Turns zurück (für Kontext-Analyse)."""
        with self._lock:
            return list(self._turns[-n:])

    def clear(self) -> None:
        """Löscht die gesamte Konversationshistorie."""
        with self._lock:
            self._turns.clear()
            self._summary = None
            logger.info("ConversationMemory[%s]: History gelöscht.", self.session_id)

    @property
    def turn_count(self) -> int:
        """Anzahl der gespeicherten Turns."""
        with self._lock:
            return len(self._turns)

    @property
    def is_empty(self) -> bool:
        """True wenn keine Turns gespeichert sind."""
        return self.turn_count == 0

    def get_context_summary(self) -> str:
        """Kompakte Zusammenfassung für Debugging / UI-Anzeige."""
        with self._lock:
            if not self._turns:
                return "(Keine Konversationshistorie)"
            last = self._turns[-1]
            return (
                f"Session '{self.session_id}': {len(self._turns)} Turns | "
                f"Letzter: '{last.user[:40]}' → '{last.assistant[:40]}'"
            )

    def __repr__(self) -> str:
        return f"ConversationMemory(session={self.session_id!r}, turns={self.turn_count})"


class ConversationMemoryManager:
    """Singleton-Manager für mehrere Konversations-Sessions.

    Jedes Chat-Widget / jeder Tab bekommt eine eigene Session-ID.
    Verhindert Speicherlecks durch automatisches Purging alter Sessions.

    Verwendung:
        manager = get_conversation_manager()
        mem = manager.get_or_create("main_chat")
        mem.add_turn(user, assistant)
    """

    def __init__(self, max_sessions: int = 5):
        self._sessions: dict[str, ConversationMemory] = {}
        self._max_sessions = max_sessions
        self._lock = threading.Lock()

    def get_or_create(
        self,
        session_id: str = "default",
        max_turns: int = MAX_TURNS_DEFAULT,
    ) -> ConversationMemory:
        """Gibt eine bestehende Session zurück oder erstellt eine neue."""
        with self._lock:
            if session_id not in self._sessions:
                # Älteste Session löschen wenn Maximum erreicht
                if len(self._sessions) >= self._max_sessions:
                    oldest = next(iter(self._sessions))
                    del self._sessions[oldest]
                    logger.info(
                        "ConversationMemoryManager: Session '%s' entfernt (Max erreicht).",
                        oldest,
                    )
                self._sessions[session_id] = ConversationMemory(
                    session_id=session_id,
                    max_turns=max_turns,
                )
                logger.debug("ConversationMemoryManager: Session '%s' erstellt.", session_id)
            return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        """Löscht eine bestimmte Session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].clear()

    def remove_session(self, session_id: str) -> None:
        """Entfernt eine Session vollständig."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear_all(self) -> None:
        """Löscht alle Sessions."""
        with self._lock:
            self._sessions.clear()

    def list_sessions(self) -> list[str]:
        """Gibt alle aktiven Session-IDs zurück."""
        with self._lock:
            return list(self._sessions.keys())

    @property
    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)


def get_conversation_manager() -> ConversationMemoryManager:
    """Gibt den modulweiten Singleton-Manager zurück."""
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = ConversationMemoryManager()
            logger.info("ConversationMemoryManager: Singleton erstellt.")
        return _manager_instance
