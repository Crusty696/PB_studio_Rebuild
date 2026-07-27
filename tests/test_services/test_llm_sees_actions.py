"""Das lokale Modell muss die registrierten Aktionen im Systemprompt sehen.

Befund 2026-07-27: ``LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS`` stand auf 1200.
Das volle Aktions-Schema misst bei 62 registrierten Aktionen 33.423 Zeichen
und riss das Budget damit immer. Der Aufbau fiel deshalb auf
``COMPACT_SYSTEM_PROMPT`` zurueck — und der enthaelt keine einzige
Aktionsliste. Das Modell konnte im JSON-Pfad also grundsaetzlich keine
Aktion aufrufen, obwohl alle 62 registriert und erreichbar waren.

Diese Tests sichern ab, dass die Aktionen sichtbar bleiben.
"""
from __future__ import annotations

import services.register_actions  # noqa: F401  — registriert alle Aktionen
from services.action_registry import action_registry


def test_compact_list_is_far_smaller_than_full_schema():
    full = action_registry.get_schema_for_prompt()
    compact = action_registry.get_compact_action_list()

    assert len(compact) < len(full) / 4, (
        f"Kompaktliste ({len(compact)}) muss deutlich kleiner sein als das "
        f"volle Schema ({len(full)}) — sonst passt sie wieder nicht ins Budget."
    )


def test_compact_list_names_every_registered_action():
    compact = action_registry.get_compact_action_list()
    missing = [n for n in action_registry.list_actions() if n not in compact]
    assert missing == [], f"Aktionen fehlen in der Kompaktliste: {missing}"


def test_built_system_prompt_contains_actions():
    """Kernbeweis: der real gebaute Prompt nennt Aktionen.

    Genau das war vorher nicht der Fall — der Fallback-Prompt war
    aktionslos.
    """
    from services.local_agent_service import LocalAgentService

    svc = LocalAgentService.__new__(LocalAgentService)
    import threading

    svc._lock = threading.RLock()
    svc.registry = action_registry
    svc._sysprompt_base_cache = None
    svc._sysprompt_media_cache = ""
    svc._sysprompt_media_ts = 0.0
    svc._sysprompt_few_shots_cache = ""
    svc._sysprompt_few_shots_ts = 0.0
    svc._build_media_context = lambda: ""
    svc._get_positive_few_shots = lambda limit=3: ""

    prompt = svc._build_system_prompt("was kannst du?")

    # Stichprobe ueber verschiedene Aktionsfamilien
    for name in ("analyze_audio", "auto_edit", "brain_recall", "list_media"):
        assert name in prompt, f"Aktion '{name}' fehlt im gebauten Systemprompt"


def test_brain_actions_are_reachable_for_any_model():
    """Die Brain-Zugriffe muessen im Tool-Whitelist des Orchestrators stehen.

    Ohne Whitelist-Eintrag bietet der Tool-Use-Loop sie einem Modell gar
    nicht an — das ist der einzige Weg, auf dem ein Modell sie real
    auswaehlen kann.
    """
    from agents.orchestrator.routing_tables import _BRAIN_SAFE_TOOLS

    for name in ("brain_recall", "brain_stats", "brain_explain_cut", "brain_learn_note"):
        assert name in _BRAIN_SAFE_TOOLS, f"'{name}' fehlt in _BRAIN_SAFE_TOOLS"
