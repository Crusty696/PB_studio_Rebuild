# 70 — Error-Surface + Recovery

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

Saubere Fehler-Behandlung pro Error-Typ. User sieht sinnvolle Messages.

## Error-Mapping

| Typ | Recovery | UI |
|---|---|---|
| Timeout | Retry × 3 mit Backoff (1s, 4s, 16s) | Spinner + "Antwortet langsam" |
| HTTPConnectionError (Daemon weg) | Watchdog-Restart + Retry × 1 | Status-Dot rot, Toast "Daemon neu starten…" |
| OOM (CUDA OOM) | Selector waehlt kleineres Modell + Retry | Toast "VRAM voll, kleineres Modell benutzt" |
| Model-not-loaded | Auto-Load + Spinner | Status-Dot orange |
| Daemon-crashed | Watchdog-Restart × 3/60s, dann Fail | Modal "LLM ausgefallen, Logs pruefen" |
| Bad-JSON-Response | JSON-Retry-Mode (siehe 18) | transparent |
| Tool-Call-Exception | strukturierter Fehler an LLM | transparent |
| HF-403 (Lizenz) | Lizenz-Akzept-Dialog erneut + Retry | Dialog |
| Disk-Full | Block Download + User-Warnung | Modal |

## Diagnose-Snapshot-Export

- Settings → "Diagnose-Bundle exportieren":
  - Letzte 1000 Log-Zeilen (Token-gescrubbt)
  - Hardware-Probe-Output
  - Installed-Models-Liste
  - DB-Versionen
  - Letzte 10 Errors mit Stacktrace
  - Zip-Datei in Downloads-Ordner

## Verifikation

- Inject OOM → kleineres Modell wird genutzt
- Inject Disk-Full → klare Message statt Crash
- `pytest tests/test_services/test_llm_errors.py -v` gruen
