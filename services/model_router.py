"""B-650 (Weg B): Zentrale, per-Aufgabe Modellwahl fuer Ollama.

Jede LLM-Aufgabe bekommt automatisch das beste installierte Modell nach
Faehigkeit (``vision`` / ``completion``) + VRAM-Fit (GTX 1060, 6 GB). Zusaetzlich
meldet jede Aufgabe ihr Modell an die UI (``ModelStatusField``), damit sichtbar
ist welches LLM je Aufgabe laeuft und dass je nach Aufgabe gewechselt wird.

Alle Szenen/Frames werden GLEICH behandelt (User-Vorgabe 2026-07-17): das
Captioning nutzt EIN Vision-Modell (das beste installierte, i.d.R. qwen3-vl);
moondream/minicpm greifen nur als Fallback, falls das beste nicht ladbar ist.
Kein Bulk/Detail-Split.

Modell-Wahl je Aufgabe (bei aktuellem Bestand):
- ``caption`` / ``vision`` -> bestes Vision-Modell (quality)   -> qwen3-vl:4b
- ``pacing``               -> bestes Text-Modell   (quality)   -> gemma3:4b
- ``action`` / ``chat``    -> schnellstes Text-Modell (speed)  -> phi3:mini

gemma4:e4b (9.6 GB) faellt automatisch durch die VRAM-Grenze in
``select_best_model`` raus — passt nicht in 6 GB.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# task -> (capability, prefer). capability: "vision"|"chat"; prefer: "quality"|"speed"
_TASK_TIERS: dict[str, tuple[str, str]] = {
    "caption": ("vision", "quality"),   # Bild-Captioning: bestes Vision-Modell
    "vision":  ("vision", "quality"),
    "pacing":  ("chat",   "quality"),   # Schnitt-Reasoning: bestes Text-Modell
    "action":  ("chat",   "speed"),     # kurze KI-Aktionen: schnellstes Text-Modell
    "chat":    ("chat",   "speed"),
}

# env-Override je Aufgabe (User-Zwang schlaegt Auto-Wahl)
_ENV_OVERRIDES: dict[str, str] = {
    "caption": "PB_VISION_MODEL",
    "vision":  "PB_VISION_MODEL",
    "pacing":  "PB_STRATEGIST_MODEL",
    "action":  "PB_OLLAMA_MODEL",
    "chat":    "PB_OLLAMA_MODEL",
}


def resolve_model_for_task(client, task: str) -> str | None:
    """Bestes installiertes Modell fuer ``task``. ``None`` wenn keins passt.

    Reihenfolge: (1) env-Override wenn installiert, (2) Auto-Wahl
    ``client.select_best_model(capability, prefer=...)``.
    """
    cap, prefer = _TASK_TIERS.get(task, ("chat", "quality"))

    env_var = _ENV_OVERRIDES.get(task)
    if env_var:
        forced = os.environ.get(env_var)
        if forced:
            try:
                if client.model_exists(forced):
                    logger.info("[MODEL-ROUTER] task=%s: env %s='%s' erzwungen.",
                                task, env_var, forced)
                    return forced
            except Exception:
                pass
            logger.warning("[MODEL-ROUTER] task=%s: %s='%s' nicht installiert -> Auto-Wahl.",
                           task, env_var, forced)

    try:
        best = client.select_best_model(cap, prefer=prefer)
    except TypeError:
        # aeltere Signatur ohne prefer
        best = client.select_best_model(cap)
    if best:
        logger.info("[MODEL-ROUTER] task=%s -> '%s' (cap=%s prefer=%s)",
                    task, best, cap, prefer)
    else:
        logger.warning("[MODEL-ROUTER] task=%s: kein passendes Modell (cap=%s).", task, cap)
    return best


def emit_task_status(phase: str, model: str, task: str) -> None:
    """Meldet Modell/Task an die UI (``ModelStatusField``). Defensiv, nie fatal.

    phase: ``"loading"`` | ``"ready"`` | ``"error"``.
    """
    try:
        from services.ollama_service import _emit_model_status
        _emit_model_status(phase, model, task)
    except Exception:
        pass
