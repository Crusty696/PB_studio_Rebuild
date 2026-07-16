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

# GTX 1060: 6 GB VRAM -> Modelle > ~5.3 GB fallen raus (laesst Platz fuer
# KV-Cache). gemma4:e4b (9.6 GB) wird so automatisch nie gewaehlt.
_MAX_VRAM_BYTES = 5_300_000_000

# "Vision-First"-Modelle: primaer fuer Bilder gebaut. Ihre Capabilities melden
# oft ZUSAETZLICH "completion", weshalb reine Capability-Pruefung sie
# faelschlich fuer Text-Aufgaben waehlt (genau der Bug: qwen3-vl fuer Chat).
# Fuer Text-Aufgaben werden diese per Namensmuster ausgeschlossen — der User
# will qwen-vl/moondream/minicpm-v NICHT fuer Text/Audio.
_VISION_FIRST_PATTERNS = ("-vl", "llava", "moondream", "minicpm-v", "bakllava")

# Bevorzugte Modell-Familien je Aufgabe (User-Zuordnung 2026-07-17). Reihenfolge
# = Prioritaet; erstes installiertes + capability-passendes + VRAM-taugliches
# Modell gewinnt. Fehlt alles davon -> generischer Fallback nach Groesse.
_TASK_PREF: dict[str, list[str]] = {
    "caption": ["qwen3-vl", "qwen2.5-vl", "minicpm-v", "moondream", "llava"],
    "vision":  ["qwen3-vl", "qwen2.5-vl", "minicpm-v", "moondream", "llava"],
    "pacing":  ["gemma3", "gemma2", "llama3.1", "llama3", "phi3", "qwen2.5"],
    "action":  ["phi3", "gemma3", "gemma2", "llama3"],
    "chat":    ["phi3", "gemma3", "gemma2", "llama3"],
}


def _is_vision_first(name: str) -> bool:
    n = name.lower()
    return any(p in n for p in _VISION_FIRST_PATTERNS)


def resolve_model_for_task(client, task: str) -> str | None:
    """Bestes installiertes Modell fuer ``task``. ``None`` wenn keins passt.

    Reihenfolge:
    1. env-Override (``PB_VISION_MODEL`` etc.) wenn installiert.
    2. Kandidaten = installierte Modelle mit passender Capability
       (``vision``/``completion``) + VRAM-Fit. Fuer Text-Aufgaben werden
       Vision-First-Modelle (qwen-vl, moondream, minicpm-v) ausgeschlossen.
    3. Ranking nach Familien-Praeferenz (``_TASK_PREF``), dann Groesse
       (quality=gross zuerst, speed=klein zuerst).
    4. Fallback: ``client.select_best_model`` (generisch).
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

    need = "vision" if cap == "vision" else "completion"
    pref = _TASK_PREF.get(task, [])
    try:
        detailed = client._list_models_detailed()
    except Exception:
        detailed = []

    candidates: list[tuple[int, int, str]] = []
    for m in detailed:
        name = m.get("name")
        if not name:
            continue
        size = int(m.get("size") or 0)
        if size and size > _MAX_VRAM_BYTES:
            continue
        try:
            caps = client._capabilities(name)
        except Exception:
            caps = None
        if caps is None:
            if need == "vision":
                continue  # Vision unbekannt -> nicht annehmen
        elif need not in caps:
            continue
        # Text-Aufgabe: Vision-First-Modelle raus (User-Regel).
        if cap == "chat" and _is_vision_first(name):
            continue
        n = name.lower()
        pref_idx = next((i for i, p in enumerate(pref) if p in n), len(pref))
        candidates.append((pref_idx, size, name))

    if candidates:
        # (pref_idx asc, dann Groesse: quality=gross zuerst / speed=klein zuerst)
        candidates.sort(key=lambda t: (t[0], -t[1] if prefer != "speed" else t[1]))
        best = candidates[0][2]
        logger.info("[MODEL-ROUTER] task=%s -> '%s' (cap=%s prefer=%s, %d Kandidaten)",
                    task, best, cap, prefer, len(candidates))
        return best

    # Fallback: generische Auswahl (kann bei Text theoretisch Vision-First
    # liefern, aber nur wenn KEIN passender Kandidat existierte).
    try:
        best = client.select_best_model(cap, prefer=prefer)
    except TypeError:
        best = client.select_best_model(cap)
    if best:
        logger.info("[MODEL-ROUTER] task=%s -> '%s' (Fallback select_best_model)", task, best)
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
