# 25 — Modell-Pins + Versionen + Re-Run-Policy

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Pro Projekt das **erste verwendete** Modell pro Rolle festpinnen. Modell-Wechsel des Users **nie** automatisches Re-Run. Modell-Version-Bump (gleiches Modell, neuere Build) manueller Re-Run-Button.

## Scope

- DB: `llm_model_pins` (siehe `01_DB_LLM_TABLES.md`).
- Auto-Pin beim ersten Modell-Use pro Rolle/Projekt.
- User kann Pin loesen (Settings → "Pin loeschen").
- DB-Artefakte aus existierenden Analysen tragen `produced_by_model` + `produced_by_model_version`.

## Re-Run-Policy

| Aktion | Verhalten |
|---|---|
| User wechselt Modell (qwen3 → llama3) | KEIN Re-Run. Alte Ergebnisse bleiben. |
| Modell-Version-Bump (qwen3:8b-q4 alt-Build → neu-Build) | Manueller "Neu mit aktuellem Modell"-Button pro Schritt. Optional. |
| Embedding-Modell-Wechsel | Suche bleibt intra-model. Hinweis "Mixed-Vector-Search aktiv". |

## UI

- Settings → Modell-Pins → pro Rolle/Projekt Anzeige + Loesch-Button.
- Analyse-Status-Panel zeigt `produced_by_model` pro Schritt.
- Per-Schritt "Neu generieren mit aktuellem Modell"-Button.

## Verifikation

- Modell-Wechsel triggert kein Re-Run
- Version-Bump erkannt + Button erscheint
- `pytest tests/test_services/test_llm_pins.py -v` gruen
