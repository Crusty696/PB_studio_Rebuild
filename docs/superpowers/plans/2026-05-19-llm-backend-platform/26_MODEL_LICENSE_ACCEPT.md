# 26 — Modell-Lizenz-Akzept-Dialog

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Vor Modell-Download: Lizenz anzeigen + Akzept einfordern. Smart-Default fuer permissive Lizenzen.

## Scope

- Lizenz-Definitionen in Registry (`licenses` Sektion).
- Pro Modell `license_id`.
- Dialog:
  - Modellname + Familie + Version
  - Lizenz-Typ Badge + Volltext-Link
  - Akzept-Checkbox
  - "Permissive immer akzeptieren" Master-Schalter (gilt fuer apache-2.0, mit, isc)
  - "Download" / "Abbrechen"
- DB: `llm_license_accepts` (siehe `01_DB_LLM_TABLES.md`).
- Re-Download: Akzept bleibt, kein neuer Dialog.
- Re-Akzept-Pflicht: bei Lizenz-Versions-Aenderung (selten).

## Smart-Default

- Apache 2.0 / MIT / ISC → "permissive_default_accepted = true" Setting → kein Dialog.
- llama-community / gemma-terms / openrail-m / cc-by-nc → immer Einzel-Dialog.
- cc-by-nc-Modelle: zusaetzliche Warnung "nicht-kommerziell".

## Verifikation

- Apache-Modell pull → kein Dialog
- Llama-Modell pull → Dialog kommt
- Cancel → kein Eintrag in `llm_license_accepts`
- `pytest tests/test_services/test_llm_license.py -v` gruen
