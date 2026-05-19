# 51 — Tier 5: Controller-Coverage-Tests (≥ 85 %)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

Pro Controller / Dialog ≥ 85 % Coverage.

## Scope

- `ui/chat_dock.py`
- `ui/dialogs/setup_wizard.py` (First-Run-Wizard)
- `ui/dialogs/settings_dialog.py` (LLM-Sektion)
- `ui/dialogs/model_manager_dialog.py`
- `ui/widgets/ai_status_dot.py`
- `ui/widgets/pacing_decision_explorer.py`
- `ui/controllers/project_management.py` (Pin-Aware)
- `ui/controllers/schnitt_controller.py` (Reasoner-Calls)

## Werkzeuge

- pytest-qt (offscreen)
- Fixture `qapp` aus SCHNITT-Plan
- Mock-LlmRequestQueue

## Verifikation

- Coverage ≥ 85 % pro Datei
- Kein blockierender UI-Test
