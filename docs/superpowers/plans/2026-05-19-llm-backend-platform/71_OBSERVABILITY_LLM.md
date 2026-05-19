# 71 — Observability (Logs, Token-Counter, Usage-Stats)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

Sichtbarkeit was wieviel Tokens / Latenz / Modell pro Anfrage.

## Scope

- Strukturiertes Log pro Request:
  - `ts, request_id, role, model_id, prompt_tokens, completion_tokens, latency_ms, ok, error`
  - Speicherung in `llm_usage_log` Tabelle + JSON-Lines `logs/llm_requests.jsonl`
- Settings → Diagnose-Tab zeigt:
  - Heutige / Wochen-Statistik pro Rolle / Modell
  - Avg-Latenz, Fail-Rate
  - "Logs leeren" Button
- Debug-Toggle:
  - "Verbose-Logs aktivieren" → erweiterte Request/Response in JSONL
  - Default off (Disk-Schutz)
- Log-Rotation:
  - JSONL pro Tag, max 30 Tage behalten
  - Komprimierung nach 7 Tagen

## Out of Scope

- Cloud-Telemetrie (Hartregel D-026 keine Cloud).

## Verifikation

- Usage-Log fuellt sich bei Calls
- Diagnose-Tab zeigt korrekte Aggregate
- Logs sind Token-gescrubbt (Pattern-Test)
- `pytest tests/test_services/test_llm_observability.py -v` gruen
