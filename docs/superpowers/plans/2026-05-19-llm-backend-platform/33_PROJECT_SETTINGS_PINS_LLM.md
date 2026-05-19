# 33 — Pro-Projekt-Modell-Pins (UI)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 3 UI
> Status: planned · 2026-05-19

## Ziel

Pro Projekt sichtbar machen welches Modell pro Rolle gepinnt ist + aenderbar.

## Scope

- Projekt-Settings-Tab:
  - Pro Rolle: aktueller Pin + Loeschen + Aendern
  - Sichtbarmachung von gemischter Provenance (z. B. "10 Captions wurden mit moondream gemacht, 5 mit minicpm-v" → Warnung)
- Pin-Setz-Logik:
  - Bei erster Nutzung pro Rolle/Projekt → Auto-Pin
  - User-manuelles Pinnen ueberschreibt Auto-Pin

## Verifikation

- Pin-Setzen reflektiert sich in `llm_model_pins`
- Mixed-Provenance Warnung erscheint korrekt
- `pytest tests/test_ui/test_project_pins.py -v` gruen
