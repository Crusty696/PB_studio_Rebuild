"""Lokaler LLM Pacing-Strategist — generiert Pacing-Plaene offline.

Nutzt Qwen2.5-1.5B-Instruct lokal via HuggingFace Transformers.
Kein Internet, keine API-Kosten. Laeuft auf GTX 1060 (6 GB VRAM).
VRAM-Sequenz: Strategist laden → Plan generieren → entladen → weiter.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STRATEGIST_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

SYSTEM_PROMPT = """\
Du bist ein DJ-Video-Pacing-Experte. Du bekommst die Struktur eines DJ-Mixes \
und musst einen Pacing-Plan erstellen der beschreibt wie Videos geschnitten werden.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt im folgenden Format:
{
  "sections": [
    {
      "type": "DROP",
      "start": 120.0,
      "end": 180.0,
      "cut_rate_beats": 2,
      "mood": "explosive",
      "notes": "Initial burst then settle"
    }
  ],
  "global_min_duration": 3.0,
  "variety_priority": 0.7
}

Regeln:
- BREAKDOWN/COOLDOWN: cut_rate_beats = 8-16, mood = ruhig/atmospheric
- DROP: cut_rate_beats = 1-2 am Anfang, dann 4, mood = explosive/energetic
- BUILDUP: cut_rate_beats abnehmend von 8 auf 1, mood = rising tension
- WARMUP: cut_rate_beats = 16, mood = atmospheric/establishing
- Clips sollten so LANG wie moeglich laufen (min 3 Sekunden)
- variety_priority: 0.0 = gleiche Clips wiederholen, 1.0 = maximale Abwechslung
"""


@dataclass
class PacingPlan:
    """LLM-generierter oder Default Pacing-Plan fuer einen Mix."""
    section_overrides: list[dict] = field(default_factory=list)
    global_min_duration: float = 3.0
    variety_priority: float = 0.7

    @classmethod
    def from_json(cls, data: dict) -> PacingPlan:
        return cls(
            section_overrides=data.get("sections", []),
            global_min_duration=data.get("global_min_duration", 3.0),
            variety_priority=data.get("variety_priority", 0.7),
        )

    @classmethod
    def default(cls) -> PacingPlan:
        """Fallback-Plan ohne LLM."""
        return cls()


class PacingStrategist:
    """Generiert Pacing-Plaene mit einem lokalen Qwen-Modell.

    Workflow:
    1. Modell laden (~3 GB VRAM, ~15s)
    2. Strukturierten Prompt mit Mix-Summary senden
    3. JSON Pacing-Plan parsen
    4. Modell entladen (VRAM frei fuer SigLIP)

    Fallback: Bei Fehler wird PacingPlan.default() zurueckgegeben.
    """

    def __init__(self, model_id: str = STRATEGIST_MODEL_ID):
        self.model_id = model_id

    def generate_pacing_plan(
        self,
        sections: list[dict],
        bpm: float,
        total_duration: float,
        clip_count: int = 0,
        user_preferences: str = "",
    ) -> PacingPlan:
        """Generiert einen Pacing-Plan basierend auf der Mix-Struktur.

        Args:
            sections: Liste von dicts mit type, start, end, avg_energy
            bpm: Beats per Minute des Tracks
            total_duration: Gesamtlaenge in Sekunden
            clip_count: Anzahl verfuegbarer Video-Clips
            user_preferences: Natuerliche Sprache vom User (z.B. "mehr Impact bei Drops")

        Returns:
            PacingPlan (Fallback auf Default bei Fehler)
        """
        # Mix-Summary fuer den Prompt aufbereiten
        sections_text = self._format_sections(sections, total_duration)

        user_prompt = (
            f"DJ-Mix Analyse:\n"
            f"- BPM: {bpm:.1f}\n"
            f"- Dauer: {total_duration:.0f}s ({total_duration/60:.1f} Minuten)\n"
            f"- Verfuegbare Video-Clips: {clip_count}\n"
            f"- Sektionen:\n{sections_text}\n"
        )
        if user_preferences:
            user_prompt += f"\nUser-Praeferenzen: {user_preferences}\n"

        user_prompt += "\nErstelle einen JSON Pacing-Plan."

        try:
            raw_response = self._generate(user_prompt)
            plan = self._parse_response(raw_response)
            logger.info("PacingStrategist: Plan generiert mit %d Section-Overrides",
                        len(plan.section_overrides))
            return plan
        except Exception as e:
            logger.warning("PacingStrategist Fehler, nutze Default-Plan: %s", e)
            return PacingPlan.default()

    def _format_sections(self, sections: list[dict], total_duration: float) -> str:
        """Formatiert Sektionen als lesbaren Text fuer den Prompt."""
        lines = []
        for sec in sections[:30]:  # Max 30 Sektionen um Prompt kurz zu halten
            s_type = sec.get("type", sec.get("section_type", "?"))
            start = sec.get("start", 0)
            end = sec.get("end", 0)
            energy = sec.get("avg_energy", sec.get("energy", 0))
            dur = end - start
            lines.append(f"  {s_type:12s} {start:6.0f}s-{end:6.0f}s ({dur:.0f}s) energy={energy:.2f}")
        if len(sections) > 30:
            lines.append(f"  ... und {len(sections) - 30} weitere Sektionen")
        return "\n".join(lines)

    def _generate(self, user_text: str) -> str:
        """Generiert Text — Ollama-first, HuggingFace als Fallback.

        Fallback-Kette:
        1. Ollama (wenn verfügbar, kein VRAM-Verbrauch)
        2. Lokales HuggingFace-Modell (Qwen2.5-1.5B, ~3 GB VRAM)
        """
        # --- Ollama-Versuch ---
        try:
            from services.ollama_client import get_ollama_client
            from ui.dialogs.settings_dialog import get_ollama_settings
            cfg = get_ollama_settings()
            if cfg.get("enabled", True):
                client = get_ollama_client(cfg.get("url", "http://localhost:11434"))
                if client.is_available():
                    model = cfg.get("model") or client.get_best_available_model()
                    if model:
                        logger.info(
                            "PacingStrategist: Nutze Ollama-Modell '%s' fuer Pacing-Plan.", model
                        )
                        result = client.chat(
                            model=model,
                            user_message=user_text,
                            system_prompt=SYSTEM_PROMPT,
                            temperature=0.1,
                            max_tokens=1024,
                        )
                        logger.info("PacingStrategist: Ollama-Antwort erhalten (%d chars)", len(result))
                        return result
        except Exception as e:
            logger.warning("PacingStrategist: Ollama nicht verfuegbar (%s) — HuggingFace-Fallback.", e)

        # --- HuggingFace-Fallback ---
        from services.model_manager import ModelManager, GPU_LOAD_LOCK

        with GPU_LOAD_LOCK:
            mm = ModelManager()

            logger.info("PacingStrategist: Lade %s...", self.model_id)
            tokenizer, model, pipe = mm.load_transformers(self.model_id)

            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ]

                if hasattr(tokenizer, "apply_chat_template"):
                    prompt = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                else:
                    prompt = f"<|system|>\n{SYSTEM_PROMPT}\n<|user|>\n{user_text}\n<|assistant|>\n"

                outputs = pipe(
                    prompt,
                    max_new_tokens=1024,
                    do_sample=False,
                    return_full_text=False,
                )
                raw = outputs[0]["generated_text"].strip()
                logger.info("PacingStrategist: Antwort erhalten (%d chars)", len(raw))
                return raw
            finally:
                mm.unload()
                logger.info("PacingStrategist: Modell entladen")

    def _parse_response(self, raw: str) -> PacingPlan:
        """Parst die JSON-Antwort des LLM."""
        # JSON aus der Antwort extrahieren (kann in Markdown-Block sein)
        json_str = raw
        if "```json" in raw:
            start = raw.index("```json") + 7
            end = raw.index("```", start)
            json_str = raw[start:end].strip()
        elif "```" in raw:
            start = raw.index("```") + 3
            end = raw.index("```", start)
            json_str = raw[start:end].strip()

        # Versuche direktes Parsing
        try:
            data = json.loads(json_str)
            return PacingPlan.from_json(data)
        except json.JSONDecodeError as e:
            logger.warning("Direct JSON parsing of LLM response failed: %s", e)

        # Fallback: Suche nach { ... } im Text
        brace_start = raw.find("{")
        brace_end = raw.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(raw[brace_start:brace_end])
                return PacingPlan.from_json(data)
            except json.JSONDecodeError as e:
                logger.warning("Fallback JSON brace-extraction from LLM response failed: %s", e)

        raise ValueError(f"Konnte kein JSON aus LLM-Antwort parsen: {raw[:200]}")
