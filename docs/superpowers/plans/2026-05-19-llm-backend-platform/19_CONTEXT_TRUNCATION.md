# 19 — Context-Length-Management + Truncation

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

History-Budget pro Modell respektieren. Lange Konversationen kuerzen, ohne wichtige System/Tool-Messages zu verlieren.

## Scope

- Token-Zaehler (tiktoken oder Modell-eigenes Tokenizer falls verfuegbar).
- Pro Modell `context_max` aus Registry.
- Truncation-Strategien:
  - **Sliding-Window:** aelteste user/assistant-Messages erst raus, system + letzte 2 Turns behalten.
  - **Summary-Injection** (optional Phase 2): aelteste Turns durch LLM-Summary ersetzen.
- Safe-Margin: 20 % Reserve fuer Antwort.

## Out of Scope

- Per-Caller History-Speicherung (existiert in `services/conversation_memory.py`).

## Verifikation

- Long-history test, geprueft dass system + letzte Turns erhalten
- Token-Counter gegen Tokenizer-Referenz
- `pytest tests/test_services/test_llm_context.py -v` gruen
