# 42 — Caller-Migration: UI-Schicht

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

UI-Konsumenten auf neue Layer umstellen.

## Scope (Reihenfolge)

1. `ui/widgets/ai_status_dot.py`            → Service-Health-API
2. `ui/dialogs/setup_wizard.py`             → integriert First-Run-Wizard (Phase 30)
3. `ui/dialogs/settings_dialog.py`          → LLM-Sektion (Phase 32)
4. `ui/dialogs/model_manager_dialog.py`     → neue Registry + Pins
5. `ui/dialogs/startup_check_dialog.py`     → neue Health-Probe
6. `ui/chat_dock.py`                        → `LlmRequestQueue` + Streaming
7. `ui/studio_brain/brain_v2_tab.py`        → Rolle `reasoner`
8. `ui/widgets/pacing_decision_explorer.py` → Rolle `reasoning_heavy`
9. `ui/controllers/panel_setup.py`          → nur Service-Calls weiterleiten
10. `ui/controllers/project_management.py`  → Pin-Aware
11. `ui/controllers/edit_workspace.py`      → Tool-Calls auf neuen Pfad
12. `ui/controllers/schnitt_controller.py`  → Reasoner-Calls
13. `ui/timeline.py`                        → Pacing-Calls auf neuen Pfad

## Strategie

- Pro UI-Komponente eigener Coverage-Test (Tier 5).
- Visuelle Verifikation am Ende von Phase 42 mit `pb-functional-tester` Skill (User-getriggert).

## Verifikation

- Chat-Dock antwortet via neuem Stack
- Status-Dot reflektiert Daemon-State
- `pytest tests/test_ui/test_llm_callers.py -v` gruen
