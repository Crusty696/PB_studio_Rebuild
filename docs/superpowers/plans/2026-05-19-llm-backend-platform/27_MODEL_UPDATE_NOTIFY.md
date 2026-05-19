# 27 — Modell-Update-Notify (manueller Check)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

User erfaehrt manuell ob ein verwendetes Modell eine neuere Version hat. Kein Auto-Polling.

## Scope

- Settings → "Modelle pruefen"-Button.
- Pro installiertem Modell:
  - Ollama-Hub: HEAD `/api/show` o.ae. → Version-Tag vergleichen
  - HF: `huggingface_hub.repo_info` → last_modified vergleichen
- Liste mit "Verfuegbares Update: ja/nein"
- Pro Update: Update-Button → Modell neu pullen, alte Datei nach Erfolg loeschen
- Update triggert **kein** Re-Run alter Artefakte (siehe `25_MODEL_PINS_AND_VERSIONS.md`).

## Out of Scope

- Auto-Polling beim Start.

## Verifikation

- Mock-Update verfuegbar → UI zeigt + Pull
- `pytest tests/test_services/test_llm_update_check.py -v` gruen
