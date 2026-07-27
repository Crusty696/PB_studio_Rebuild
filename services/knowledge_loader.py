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
import threading
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


# ---------------------------------------------------------------------------
# B-738 — Brain-Gedaechtnis OHNE Tool-Support
# ---------------------------------------------------------------------------
# Die vier Brain-Actions (brain_recall/brain_stats/brain_explain_cut/
# brain_learn_note) sind zwar in der Tool-Whitelist des Orchestrators, aber
# nur der tool-faehige Pfad ruft sie auf. Plain-Chat, der Pacing- und der
# Vision-Pfad — und jedes Modell ohne Tool-Support (phi3, gemma) — kamen an
# die gespeicherten Erkenntnisse gar nicht heran.
#
# ``build_brain_context()`` ist der tool-unabhaengige Weg: es liest dieselbe
# Quelle wie ``brain_recall`` und liefert einen kurzen Prompt-Block. Bewusst
# hier und nicht in ``local_agent_service`` — so kann jeder Pfad das
# Gedaechtnis einspeisen, ohne den Chat-Service zu importieren.
#
# BUDGET: der System-Prompt hat 12.000 Zeichen, davon belegt die kompakte
# Aktionsliste schon rund 8.600 (gemessen 2026-07-27, 62 Aktionen). Der
# Brain-Block ist deshalb hart gedeckelt — er darf die Aktionsliste NIE
# wieder aus dem Prompt draengen (Regression gegen Commit 5a0ac3c).
BRAIN_CONTEXT_MAX_CHARS = 1200
BRAIN_CONTEXT_TOP_K = 3


def _fmt_brain_item(item: dict) -> str | None:
    """Ein Recall-Treffer als EINE kurze Prompt-Zeile."""
    source = item.get("source")
    if source == "brain_note":
        title = str(item.get("title") or "").strip()
        body = " ".join(str(item.get("body") or "").split())[:180]
        return f"- Notiz \"{title}\": {body}" if (title or body) else None
    if source == "mem_learned_pattern":
        return (
            f"- Muster {item.get('pattern_type')} "
            f"[{item.get('context_fingerprint')}] -> {item.get('target_ref')} "
            f"({item.get('accepts', 0)}x akzeptiert / "
            f"{item.get('rejects', 0)}x abgelehnt, "
            f"Konfidenz {float(item.get('confidence') or 0.0):.2f})"
        )
    if source == "mem_decision":
        verdict = item.get("user_verdict") or "ohne Urteil"
        return (
            f"- Schnitt in {item.get('at_section_type') or '?'}"
            f"/{item.get('at_genre') or '?'}: Rolle "
            f"{item.get('clip_role') or '?'}, Mood "
            f"{item.get('clip_mood_refined') or '?'} -> {verdict}"
        )
    return None


def build_brain_context(
    query: str = "",
    max_chars: int = BRAIN_CONTEXT_MAX_CHARS,
    top_k: int = BRAIN_CONTEXT_TOP_K,
) -> str:
    """Baut einen kurzen, query-relevanten Block aus dem Brain-Gedaechtnis.

    Args:
        query: Nutzerfrage. Steuert die Relevanz-Auswahl in ``brain_recall``.
        max_chars: harte Obergrenze des erzeugten Blocks.
        top_k: Treffer pro Quelle in ``brain_recall``.

    Returns:
        Prompt-Block oder "" — leer, wenn nichts gespeichert ist oder die
        Abfrage fehlschlaegt. Ein leerer Block ist immer zulaessig; der
        Prompt bleibt dann exakt so wie vorher.
    """
    if max_chars <= 0:
        return ""
    try:
        from services.actions.brain_actions import brain_recall

        result = brain_recall(query=query or "", top_k=max(1, int(top_k)))
    except Exception as exc:  # broad: Brain-Kontext ist nie kritisch
        logger.debug("Brain-Kontext nicht ladbar: %s", exc)
        return ""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return ""
    results = result.get("results") or []
    if not results:
        return ""

    header = (
        "## BRAIN-GEDAECHTNIS (selbst gelernt, nutze das statt zu raten)"
    )
    lines: list[str] = [header]
    used = len(header)
    for item in results:
        line = _fmt_brain_item(item) if isinstance(item, dict) else None
        if not line:
            continue
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


# Modul-Singleton (lazy, thread-safe)
_loader: KnowledgeLoader | None = None
_loader_lock = threading.Lock()


def get_knowledge_loader() -> KnowledgeLoader:
    """Gibt den modulweiten Knowledge-Loader zurück (Singleton, thread-safe)."""
    global _loader
    if _loader is None:
        with _loader_lock:
            if _loader is None:
                _loader = KnowledgeLoader()
    return _loader
