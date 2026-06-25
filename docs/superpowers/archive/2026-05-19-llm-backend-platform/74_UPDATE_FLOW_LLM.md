# 74 — Update-Flow (App-Update behaelt Modelle)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

PB-Studio-Update tauscht App-Binary + Ollama-Binary (gepinnte Version pro Release), Modelle bleiben unter `%APPDATA%`.

## Scope

- Pinned-Ollama-Version pro PB-Release in `pyproject.toml` (`ollama_pinned_version`) + Hash.
- Bei App-Start: Version-Check, wenn lokale Ollama-Version != pinned → ersetzen.
- Modelle ueberleben in `%APPDATA%/PBStudio/llm/ollama/`.
- Settings ueberleben (Migrations falls Schema-Bump in `01_DB_LLM_TABLES.md`).
- Migrations-Engine wie SCHNITT A16 — idempotent + Version-Key.

## Verifikation

- App v1 → v2 Update: Modelle weiter da, Daemon-Version aktualisiert
- DB-Schema-Migration laeuft
- `pytest tests/test_services/test_llm_update_flow.py -v` gruen
