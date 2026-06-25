# 17 — Tool-Calling

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

LLM kann App-Funktionen aufrufen (z. B. "fuege Clip an Position X ein"). Result wird zurueck-gefuettert.

## Scope

- OpenAI-tools-Schema (JSON-Schema).
- `services/llm/tools/registry.py` — App-Funktionen registrieren:
  ```python
  @tool(name="add_clip_to_timeline", schema={...})
  def add_clip_to_timeline(clip_id: str, position_s: float) -> dict: ...
  ```
- Router:
  - LLM streamt `tool_calls` → Queue erkennt, ruft Tool, Result als Tool-Message zurueck an LLM.
  - Multi-Turn-Tool-Calls supportet.
- Error-Handling:
  - Tool wirft Exception → LLM bekommt strukturiert `{"error": "..."}`.
  - LLM darf retry oder Stop entscheiden.
- Fallback fuer Modelle ohne native Tool-Support:
  - JSON-Mode mit hint-Prompt → Parse-Layer extrahiert Tool-Call.

## Out of Scope

- Konkrete App-Tool-Liste (kommt in Caller-Migration `41_*`).

## Verifikation

- Schema-Validation
- Round-trip Tool-Call mit Mock-Tool
- `pytest tests/test_services/test_llm_tools.py -v` gruen
