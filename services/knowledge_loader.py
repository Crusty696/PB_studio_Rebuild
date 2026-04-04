"""
Knowledge-Base Loader für PB Studio.

Lädt Domain-Wissen aus dem knowledge/ Ordner und injiziert es
als Kontext in LLM-System-Prompts.

Architektur:
- Markdown-Dateien in knowledge/ sind das "Langzeit-Gedächtnis" der KI
- KnowledgeLoader lädt relevante Dateien basierend auf dem Kontext
- Der Inhalt wird komprimiert in den System-Prompt eingebettet
- AIPacingMemory (DB) ist das "Kurzzeit-Gedächtnis" (gelernte Regeln)

Verwendung:
    loader = KnowledgeLoader()
    context = loader.build_context(query="Drop-Erkennung")
    system_prompt = base_prompt + "\\n\\n" + context
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Knowledge-Basis-Verzeichnis (relativ zu diesem File)
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# Maximale Zeichen des Knowledge-Kontexts im Prompt
# (zu viele Tokens verlangsamen Inference und überschreiten Context-Window)
MAX_CONTEXT_CHARS = 4000

# Keyword-zu-Datei Mapping für gezieltes Laden
_KEYWORD_FILE_MAP: dict[str, list[str]] = {
    # DJ-Set-Struktur
    "drop": ["dj_set_structure.md", "pacing_rules.md"],
    "buildup": ["dj_set_structure.md", "pacing_rules.md"],
    "breakdown": ["dj_set_structure.md", "pacing_rules.md"],
    "warmup": ["dj_set_structure.md", "pacing_rules.md"],
    "intro": ["dj_set_structure.md"],
    "cooldown": ["dj_set_structure.md"],
    "sektion": ["dj_set_structure.md"],
    "section": ["dj_set_structure.md"],
    "transition": ["dj_set_structure.md"],

    # Pacing
    "pacing": ["pacing_rules.md"],
    "schnitt": ["pacing_rules.md"],
    "cut": ["pacing_rules.md"],
    "beat": ["pacing_rules.md", "audio_analysis.md"],
    "bpm": ["pacing_rules.md", "audio_analysis.md"],
    "energie": ["pacing_rules.md"],
    "energy": ["pacing_rules.md"],
    "vocal": ["pacing_rules.md", "audio_analysis.md"],
    "ducking": ["pacing_rules.md"],

    # Audio-Analyse
    "stem": ["audio_analysis.md"],
    "drums": ["audio_analysis.md"],
    "bass": ["audio_analysis.md"],
    "analyse": ["audio_analysis.md", "pb_studio_capabilities.md"],
    "analyze": ["audio_analysis.md", "pb_studio_capabilities.md"],
    "lufs": ["audio_analysis.md"],
    "frequenz": ["audio_analysis.md"],
    "demucs": ["audio_analysis.md"],

    # Video-Matching
    "video": ["video_matching.md", "pb_studio_capabilities.md"],
    "clip": ["video_matching.md", "pacing_rules.md"],
    "motion": ["video_matching.md"],
    "siglip": ["video_matching.md"],
    "mood": ["video_matching.md"],
    "proxy": ["video_matching.md"],

    # Allgemein
    "auto-edit": ["pb_studio_capabilities.md", "pacing_rules.md"],
    "auto edit": ["pb_studio_capabilities.md", "pacing_rules.md"],
    "aktion": ["pb_studio_capabilities.md"],
    "action": ["pb_studio_capabilities.md"],
    "export": ["pb_studio_capabilities.md", "video_matching.md"],
    "render": ["pb_studio_capabilities.md", "video_matching.md"],
    "gpu": ["pb_studio_capabilities.md"],
    "vram": ["pb_studio_capabilities.md"],
}


class KnowledgeLoader:
    """Lädt und verwaltet das Domain-Wissen von PB Studio.

    Ermöglicht kontext-sensibles Laden: Nur relevante Knowledge-Dateien
    werden geladen, um den Prompt nicht zu überladen.
    """

    def __init__(self, knowledge_dir: Path | None = None):
        self.knowledge_dir = knowledge_dir or KNOWLEDGE_DIR
        self._cache: dict[str, str] = {}  # Dateiname → Inhalt (im Speicher gecacht)

    def get_available_files(self) -> list[Path]:
        """Gibt alle verfügbaren Knowledge-Dateien zurück."""
        if not self.knowledge_dir.exists():
            logger.warning("Knowledge-Verzeichnis nicht gefunden: %s", self.knowledge_dir)
            return []
        return sorted(self.knowledge_dir.glob("*.md"))

    def load_file(self, filename: str) -> str:
        """Lädt eine Knowledge-Datei (gecacht)."""
        if filename in self._cache:
            return self._cache[filename]

        path = self.knowledge_dir / filename
        if not path.exists():
            logger.debug("Knowledge-Datei nicht gefunden: %s", path)
            return ""

        try:
            content = path.read_text(encoding="utf-8")
            self._cache[filename] = content
            return content
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.warning("Fehler beim Lesen von %s: %s", filename, e)
            return ""

    def _find_relevant_files(self, query: str) -> list[str]:
        """Bestimmt relevante Knowledge-Dateien für eine Query."""
        query_lower = query.lower()
        relevant: set[str] = set()

        for keyword, files in _KEYWORD_FILE_MAP.items():
            if keyword in query_lower:
                relevant.update(files)

        # Fallback: pb_studio_capabilities.md immer laden (Aktions-Dokumentation)
        if not relevant:
            relevant.add("pb_studio_capabilities.md")

        return sorted(relevant)

    def build_context(
        self,
        query: str = "",
        max_chars: int = MAX_CONTEXT_CHARS,
        always_include: list[str] | None = None,
    ) -> str:
        """Baut einen Knowledge-Kontext-String für den System-Prompt.

        Args:
            query: Benutzeranfrage (für relevante Datei-Auswahl)
            max_chars: Maximale Zeichenanzahl des Kontexts
            always_include: Dateien die immer geladen werden

        Returns:
            Formatierter Kontext-String für den System-Prompt
        """
        relevant_files = self._find_relevant_files(query)

        if always_include:
            for f in always_include:
                if f not in relevant_files:
                    relevant_files.insert(0, f)

        if not relevant_files:
            return ""

        sections: list[str] = []
        total_chars = 0

        for filename in relevant_files:
            content = self.load_file(filename)
            if not content:
                continue

            # Komprimieren: Leere Zeilen reduzieren, Tabellen kürzen
            compressed = self._compress_content(content, max_chars // len(relevant_files))

            if total_chars + len(compressed) > max_chars:
                # Nur noch so viele Zeichen wie Platz übrig
                remaining = max_chars - total_chars
                if remaining > 200:
                    compressed = compressed[:remaining] + "\n[... gekürzt]"
                else:
                    break

            sections.append(compressed)
            total_chars += len(compressed)

        if not sections:
            return ""

        context = (
            "## DOMAIN-WISSEN (PB Studio Knowledge-Base)\n\n"
            + "\n\n---\n\n".join(sections)
        )
        return context

    def build_full_context(self, max_chars: int = MAX_CONTEXT_CHARS * 2) -> str:
        """Lädt ALLE Knowledge-Dateien (für initiale System-Prompt-Befüllung)."""
        all_files = [f.name for f in self.get_available_files()]
        sections: list[str] = []
        total_chars = 0

        for filename in all_files:
            content = self.load_file(filename)
            if not content:
                continue
            compressed = self._compress_content(content, max_chars // max(len(all_files), 1))
            if total_chars + len(compressed) > max_chars:
                break
            sections.append(compressed)
            total_chars += len(compressed)

        if not sections:
            return ""

        return (
            "## DOMAIN-WISSEN (PB Studio Knowledge-Base)\n\n"
            + "\n\n---\n\n".join(sections)
        )

    @staticmethod
    def _compress_content(content: str, max_chars: int) -> str:
        """Komprimiert Markdown-Inhalt für Prompt-Effizienz."""
        # Mehrfache Leerzeilen auf eine reduzieren
        content = re.sub(r'\n{3,}', '\n\n', content)
        # Code-Block-Kommentare kürzen
        content = re.sub(r'```python\n.*?```', '[Python-Code]', content, flags=re.DOTALL)
        # Sehr lange Tabellen kürzen
        lines = content.split('\n')
        if len(lines) > 80:
            lines = lines[:70] + [f"[... {len(lines) - 70} weitere Zeilen]"]
            content = '\n'.join(lines)
        # Auf max_chars beschränken
        if len(content) > max_chars:
            content = content[:max_chars] + "\n[... gekürzt]"
        return content.strip()

    def invalidate_cache(self) -> None:
        """Leert den Datei-Cache (nach Änderungen an Knowledge-Dateien)."""
        self._cache.clear()
        logger.info("KnowledgeLoader: Cache geleert.")

    def get_summary(self) -> dict:
        """Gibt eine Zusammenfassung der geladenen Knowledge-Basis zurück."""
        files = self.get_available_files()
        total_chars = sum(len(self.load_file(f.name)) for f in files)
        return {
            "files": [f.name for f in files],
            "file_count": len(files),
            "total_chars": total_chars,
            "knowledge_dir": str(self.knowledge_dir),
        }


# Modul-Singleton (lazy)
_loader: KnowledgeLoader | None = None


def get_knowledge_loader() -> KnowledgeLoader:
    """Gibt den modulweiten Knowledge-Loader zurück (Singleton)."""
    global _loader
    if _loader is None:
        _loader = KnowledgeLoader()
    return _loader
