# 30 — First-Run-Wizard

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 3 UI
> Status: planned · 2026-05-19

## Ziel

Erster App-Start nach Install ohne Modelle: User wird durch Auswahl + Download gefuehrt.

## Scope

- Detect: `llm_models_installed` leer → Wizard.
- Schritte:
  1. Begruessung + Erklaerung
  2. HF-Token (optional, kann uebersprungen werden)
  3. Modell-Wahl pro Rolle (Auto-Vorschlag aus Registry passend zur 1060)
  4. Lizenz-Akzept pro Modell (Smart-Default permissive)
  5. Pull-Progress (parallel oder sequentiell)
  6. Smoke-Test (ein Chat-Call) → Status OK
  7. Fertig → Main-UI
- Offline-Handling: kein Internet → "Modelle koennen spaeter geladen werden, App funktioniert eingeschraenkt"
- Abbruch-Pfad: User kann jederzeit Skip → App startet ohne Modelle (LLM-Features deaktiviert).

## Verifikation

- Cleaner Install + First-Run → Walkthrough ohne Fehler
- Skip-Pfad → App startet
- `pytest tests/test_ui/test_first_run_wizard.py -v` gruen
