# 18 — JSON-Mode + Structured Output

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Strukturierte Antworten (Pacing-Plan, Tag-Set, Cut-Liste) garantieren via JSON-Schema.

## Scope

- Pro Rolle/Anwendungsfall ein Pydantic-Modell (oder TypedDict):
  - `PacingPlan`, `CutList`, `CaptionSet`, `TagSet`, `SectionMap`.
- API-Call mit `format="json"` (Ollama-nativ) oder `response_format={"type":"json_object"}` (OpenAI).
- Parse + Validate via Pydantic. Bei Fehler:
  - Retry mit Hint-Prompt "Antwort war kein valides JSON: <error>. Bitte korrigiere."
  - max 2 Retries, danach Fail.
- JSON-Schema-Mode wenn vom Modell supportet (`format: { ... json-schema ... }`).

## Out of Scope

- Aufrufer-spezifische Schemas — pro Caller im Caller-Migration-Plan.

## Verifikation

- Mock-Bad-JSON → Retry → Success
- Mock-Definitely-Bad → 2 Retries → Fail mit klarer Message
- `pytest tests/test_services/test_llm_json_mode.py -v` gruen
