"""Orchestrator-Submodule (AUFRAEUM B2 — konservativer God-Object-Split).

Enthaelt zustandsarme, kohaesive Teile die aus
``agents/orchestrator_agent.py`` verbatim ausgelagert wurden:

- ``prompts``: System-Prompts fuer Klassifizierung / Tool-Use / General-Chat.
- ``routing_tables``: Keyword-/Tool-Dispatch-Tabellen fuer das Routing.

Die oeffentliche API (Klasse ``OrchestratorAgent`` + alle bisherigen
Modul-Namen) bleibt unveraendert ueber ``agents.orchestrator_agent``
erreichbar — dieses Package fuegt nur interne Struktur hinzu, kein
Logik-Change.
"""
