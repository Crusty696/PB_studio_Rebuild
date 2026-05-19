# 76 — Per-Projekt LLM-Praeferenzen

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

Pro Projekt eigene Modell-Praeferenzen / Pins / Lizenz-Akzept-Scope.

## Scope

- DB-Tabellen siehe `01_DB_LLM_TABLES.md` (`llm_model_pins`).
- Projekt-Settings-UI siehe `33_PROJECT_SETTINGS_PINS_LLM.md`.
- Override-Reihenfolge:
  1. Projekt-Pin
  2. Global-Default (Settings)
  3. Auto-Selector
- Beim Projekt-Open: aktive Pins laden.
- Beim Projekt-Wechsel: Slot wechseln (Hot-Reload, siehe 28).

## Verifikation

- Projekt A nutzt qwen3, Projekt B nutzt llama3 — Wechsel respektiert beide
- `pytest tests/test_services/test_llm_per_project.py -v` gruen
