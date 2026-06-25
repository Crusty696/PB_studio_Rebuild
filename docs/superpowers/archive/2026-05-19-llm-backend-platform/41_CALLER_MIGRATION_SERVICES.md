# 41 — Caller-Migration: Services-Schicht

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

Alle Service-Schicht-Caller von altem `ollama_service` auf `services/llm/` umstellen.

## Scope (Reihenfolge)

1. `services/local_agent_service.py`        → benutzt `LlmRequestQueue`
2. `services/brain_v2/reasoner.py`          → Rolle `reasoner` / `reasoning_heavy`
3. `services/pacing_strategist.py`          → Rolle `reasoning_heavy`
4. `services/video_analysis_service.py`     → Rolle `vision` fuer Caption, `reasoner` fuer Tags
5. `services/conversation_memory.py`        → Rolle `embeddings` (CPU)
6. `services/model_manager.py`              → uebernimmt neue Registry
7. `services/model_lifecycle_service.py`    → DB-Persistence + Pin-Lookup
8. `services/actions/ai_actions.py`         → Tool-Calls via neue `tools/registry`
9. `agents/orchestrator_agent.py`           → Rolle `reasoner` + Tools
10. `services/startup_checks.py`            → neue Daemon-Health-Probe

## Strategie

- **Atomic-Switch pro Caller** mit TDD:
  - RED: Test gegen neuen Layer schreiben (Mock-Backend)
  - GREEN: Caller umstellen
  - REFACTOR: alte Imports entfernen
- **Backward-compat-Adapter** in `services/llm/legacy_compat.py` fuer schwierige Caller, max 2 Wochen.
- Nach 41 abgeschlossen: `services/ollama_service.py` + `ollama_client.py` als deprecated markiert (warnen bei Import), in Phase 42 vollstaendig entfernt.

## Verifikation

- Pro Caller eigene Service-Coverage-Tests (≥ 85 %)
- Integration-Test mit Mock-Daemon
- Alte Service-Module nicht mehr importiert
