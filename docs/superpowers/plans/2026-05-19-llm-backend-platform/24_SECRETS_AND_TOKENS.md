# 24 — Secrets + Tokens (Keyring + DPAPI)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

HF-Token sicher speichern. Niemals in Logs / Settings.json / Crash-Reports.

## Scope

- `keyring`-Library, Backend Windows Credential Manager.
- Service-Name: `pb-studio-llm`.
- Schluessel: `hf_token`.
- Fallback: AES-encrypted Datei `%APPDATA%/PBStudio/secrets.enc` mit DPAPI-Key (User-bound).
- Token-UI in Settings:
  - Eingabe (Passwort-Feld)
  - "Test"-Button (HF-API-Call `/api/whoami-v2`)
  - "Loeschen"
- Token-Read nur in HTTP-Client-Konstruktor + an `huggingface_hub` Subprozess-Env. Niemals in QSettings.

## Log-Scrubber

- Custom-Log-Filter:
  - Pattern `hf_[A-Za-z0-9]{20,}` → `hf_***REDACTED***`
  - Authorization-Header → `Authorization: Bearer ***`
- Crash-Handler wendet Scrubber auf Traceback an.

## Out of Scope

- CivitAI-Token (out of scope laut User-Entscheidung).

## Verifikation

- Token nach `app_close + app_open` weiter gueltig (Keyring persistiert)
- Falsches Token → klare Fehlermeldung
- Logs nach Test grep'd auf Token-Pattern → 0 Treffer
- `pytest tests/test_services/test_llm_secrets.py -v` gruen
