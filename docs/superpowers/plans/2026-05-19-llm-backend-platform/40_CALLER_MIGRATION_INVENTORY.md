# 40 — Caller-Migration Inventar

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Caller-Migration
> Status: planned · 2026-05-19

## Ziel

Liste aller heutigen `ollama_service` / `ollama_client` / `local_agent_service` / direkter HTTP-Aufrufe.

## Scope

Audit-Ziel-Verzeichnisse:

- `services/ollama_service.py`
- `services/ollama_client.py`
- `services/local_agent_service.py`
- `services/brain_v2/reasoner.py`
- `services/video_analysis_service.py`
- `services/pacing_strategist.py`
- `services/conversation_memory.py`
- `services/model_manager.py`
- `services/model_lifecycle_service.py`
- `services/actions/ai_actions.py`
- `services/startup_checks.py`
- `agents/orchestrator_agent.py`
- `ui/chat_dock.py`
- `ui/studio_brain/brain_v2_tab.py`
- `ui/widgets/ai_status_dot.py`
- `ui/widgets/pacing_decision_explorer.py`
- `ui/dialogs/model_manager_dialog.py`
- `ui/dialogs/settings_dialog.py`
- `ui/dialogs/setup_wizard.py`
- `ui/dialogs/startup_check_dialog.py`
- `ui/controllers/panel_setup.py`
- `ui/controllers/project_management.py`
- `ui/controllers/edit_workspace.py`
- `ui/controllers/schnitt_controller.py`
- `ui/timeline.py`

## Deliverable

`docs/superpowers/plans/2026-05-19-llm-backend-platform/_artifacts/caller_inventory.md` mit:
- Pro Caller: Datei:Zeile, gerufene Funktion (chat/embed/list_models), Rolle, ob streaming.
- Migration-Schwierigkeit (low/mid/high).
- Test-Coverage-Status.

## Verifikation

- Vollstaendigkeit: `grep -r "ollama"` listet keine nicht-migrierten Caller mehr nach Phase 41+42.
