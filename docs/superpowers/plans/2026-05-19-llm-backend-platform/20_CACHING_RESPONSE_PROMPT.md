# 20 — Caching (Response + Prompt-Cache)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Deterministische Prompts (Captions, Tags) sollen Cache-Treffer haben. Ollama-Prompt-Cache nutzen.

## Scope

- **Response-Cache** (`services/llm/cache.py`):
  - Key: `sha256(model_id + role + prompt + params)`.
  - Value: vollstaendige Antwort + Metadaten.
  - SQLite-Tabelle `llm_response_cache` (size-limited, LRU).
- **Prompt-Cache** (Ollama):
  - `keep_alive` Parameter steuern: 60 s default.
  - System-Prompt + Tools constant → Ollama cached intern Prefix.
- **Cache-Invalidation:** bei Modell-Wechsel die Eintraege mit `produced_by_model = old` weiter lesbar lassen aber nicht mehr matchen (Key enthaelt Modell-ID).

## Out of Scope

- Embedding-Cache — siehe `21_EMBEDDINGS_AND_VECTOR_STORE.md`.

## Verifikation

- Zwei identische Prompts → 2. trifft Cache, < 50 ms
- Modell-Wechsel → kein falscher Hit
- `pytest tests/test_services/test_llm_cache.py -v` gruen
