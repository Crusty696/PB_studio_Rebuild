"""Lokaler LLM Pacing-Strategist — generiert Pacing-Plaene offline.

Nutzt Gemma 4 E4B via Ollama. Kein Internet, keine API-Kosten.
Fallback: PacingPlan.default() wenn Ollama nicht verfuegbar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# B-241: ``gemma4:e4b`` war ein Phantom-Tag (existiert nicht in Ollama).
# Module-Konstante bleibt als Fallback (``gemma3:4b`` ist ein echter Tag),
# Aufrufer sollten ``get_strategist_model()`` nutzen — das resolved live
# gegen die installierten Modelle.
STRATEGIST_MODEL_ID = "gemma3:4b"


def get_strategist_model() -> str:
    """Liefert das aktive Strategist-Modell, live aufgeloest.

    Reihenfolge:
    1. ``PB_STRATEGIST_MODEL`` env-var (User-Override)
    2. ``OllamaService.get_default_model()`` (Family-Match auf gemma4
       oder erstes installiertes Modell)
    3. ``STRATEGIST_MODEL_ID`` als Fallback
    """
    import os
    env_override = os.environ.get("PB_STRATEGIST_MODEL")
    if env_override:
        return env_override
    try:
        from services.ollama_service import OllamaService
        model = OllamaService.get().get_default_model()
        if model:
            return model
    except Exception as e:
        logger.debug("Strategist-Default-Lookup fehlgeschlagen: %s", e)
    return STRATEGIST_MODEL_ID

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
    degraded: bool = False
    degraded_reason: str = ""

    @classmethod
    def from_json(cls, data: dict) -> PacingPlan:
        """B-075: defensive Validation gegen halluzinierten LLM-Output.

        Vorher wurde JEDES syntaktisch gueltige JSON akzeptiert. Negative
        ``cut_rate_beats``, Strings wo Floats erwartet werden,
        unbekannte ``type``-Werte → silent Timeline-Korruption oder
        Crash im Auto-Edit-Inneren.

        Wir validieren auf der Eingangsseite und droppen kaputte
        Section-Eintraege statt sie durchzureichen. Konservative Werte:
        - ``cut_rate_beats`` ∈ [1, 32] (sonst entfernen)
        - ``global_min_duration`` ∈ [0.5, 30.0]
        - ``variety_priority`` ∈ [0.0, 1.0]
        - ``type`` muss in der Pacing-Map-Whitelist sein
        - ``start`` / ``end`` muessen Floats sein
        """
        _ALLOWED_TYPES = {
            "INTRO", "WARMUP", "BUILDUP", "DROP",
            "BREAKDOWN", "TRANSITION", "COOLDOWN", "OUTRO",
        }
        # Section-Overrides validieren — kaputte Eintraege verwerfen.
        clean_sections: list[dict] = []
        raw_sections = data.get("sections")
        if isinstance(raw_sections, list):
            for sec in raw_sections:
                if not isinstance(sec, dict):
                    continue
                stype = sec.get("type")
                if not isinstance(stype, str) or stype not in _ALLOWED_TYPES:
                    continue
                # cut_rate_beats: muss positive int in [1, 32] sein
                cr = sec.get("cut_rate_beats")
                try:
                    cr_int = int(cr) if cr is not None else None
                except (TypeError, ValueError):
                    cr_int = None
                if cr_int is not None and not (1 <= cr_int <= 32):
                    cr_int = None  # kaputter Wert → droppe das Feld
                # start / end optional — wenn da, muessen es Floats sein
                cleaned: dict = {"type": stype}
                if cr_int is not None:
                    cleaned["cut_rate_beats"] = cr_int
                for f in ("start", "end"):
                    v = sec.get(f)
                    try:
                        if v is not None:
                            cleaned[f] = max(0.0, float(v))
                    except (TypeError, ValueError):
                        pass
                if "mood" in sec and isinstance(sec["mood"], str):
                    cleaned["mood"] = sec["mood"]
                if "notes" in sec and isinstance(sec["notes"], str):
                    cleaned["notes"] = sec["notes"]
                clean_sections.append(cleaned)

        # global_min_duration: clamp [0.5, 30.0]
        gmd = data.get("global_min_duration", 3.0)
        try:
            gmd_f = float(gmd)
        except (TypeError, ValueError):
            gmd_f = 3.0
        gmd_f = max(0.5, min(30.0, gmd_f))

        # variety_priority: clamp [0.0, 1.0]
        vp = data.get("variety_priority", 0.7)
        try:
            vp_f = float(vp)
        except (TypeError, ValueError):
            vp_f = 0.7
        vp_f = max(0.0, min(1.0, vp_f))

        return cls(
            section_overrides=clean_sections,
            global_min_duration=gmd_f,
            variety_priority=vp_f,
        )

    @classmethod
    def default(cls) -> PacingPlan:
        """Fallback-Plan ohne LLM."""
        return cls()


class PacingStrategist:
    """Generiert Pacing-Plaene mit Gemma 4 E4B via Ollama.

    Workflow:
    1. Prompt mit Mix-Summary an Ollama senden
    2. JSON Pacing-Plan parsen
    3. Fallback: PacingPlan.default() wenn Ollama nicht verfuegbar
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
        max_tokens: int | None = None,
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

        # B-163: Token-Budget proportional zu Section-Count berechnen.
        # Pro Section-Override-Object ~60 Tokens (type/start/end/cut_rate/mood/notes
        # + JSON-Overhead). Plus 200 Tokens fuer den Hauptobjekt-Boilerplate.
        if max_tokens is None:
            estimated = 200 + len(sections) * 60
            max_tokens = min(4096, max(1024, estimated))

        try:
            raw_response = self._generate(user_prompt, max_tokens=max_tokens)
            plan = self._parse_response(raw_response)
            logger.info("PacingStrategist: Plan generiert mit %d Section-Overrides",
                        len(plan.section_overrides))
            return plan
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("PacingStrategist Fehler, nutze Default-Plan: %s", e)
            plan = PacingPlan.default()
            plan.degraded = True
            plan.degraded_reason = f"ollama_unavailable:{e}"
            return plan

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

    def _generate(self, user_text: str, max_tokens: int = 1024) -> str:
        """Generiert Text via Ollama (Gemma 4 E4B).

        Raises RuntimeError wenn Ollama nicht verfuegbar — Caller
        faengt das ab und nutzt PacingPlan.default().

        B-163: max_tokens ist jetzt parametrisiert. generate_pacing_plan
        skaliert das Budget proportional zur Section-Count damit lange
        DJ-Mixes nicht mid-JSON abschneiden.
        """
        from services.ollama_client import get_ollama_client
        from ui.dialogs.settings_dialog import get_ollama_settings

        cfg = get_ollama_settings()
        if not cfg.get("enabled", True):
            raise RuntimeError("Ollama ist deaktiviert in den Einstellungen")

        client = get_ollama_client(cfg.get("url", "http://localhost:11434"))
        if not client.is_available():
            raise RuntimeError("Ollama-Server nicht erreichbar")

        model = cfg.get("model") or client.get_best_available_model()
        if not model:
            raise RuntimeError("Kein Ollama-Modell verfuegbar")

        logger.info("PacingStrategist: Nutze Ollama '%s' fuer Pacing-Plan.", model)
        result = client.chat(
            model=model,
            user_message=user_text,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        logger.info("PacingStrategist: Antwort erhalten (%d chars)", len(result))
        return result

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
