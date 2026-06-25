# 72 — Security (Bind / Env / Single-Instance / Outbound)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

Minimaler Angriffsflaeche. Keine externe Zugriffsmoeglichkeit.

## Scope

### Bind-Adresse
- Ollama-Daemon ausschliesslich `127.0.0.1:<random_port>`. Niemals `0.0.0.0`.
- Bei Bind-Fehler: App startet nicht (kein Fallback auf 0.0.0.0).

### Subprozess-Env
- Whitelist statt ganze `os.environ` vererben:
  - `PATH`, `SystemRoot`, `TEMP`, `TMP`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `PROGRAMDATA`
  - `OLLAMA_HOST`, `OLLAMA_MODELS`, `OLLAMA_NO_TELEMETRY=1`, `CUDA_VISIBLE_DEVICES=0`
- Token-Variablen (`HUGGINGFACE_HUB_TOKEN`) nur in HF-Downloader-Subprozess, niemals in Ollama-Subprozess.

### Outbound-Whitelist
- HTTP-Client erlaubt nur:
  - `127.0.0.1` (Daemon)
  - `huggingface.co`, `*.huggingface.co`, `cdn-lfs.huggingface.co`
  - `registry.ollama.ai`, `ollama.com` (Modell-Pull)
- Allg. Internet-Zugriff: blockiert (via httpx-Hook).

### Single-Instance-Lock
- `QLockFile` in `%APPDATA%/PBStudio/pb_studio.lock`.
- Beim Start: try-lock. Wenn schon gehalten → bring existing instance to front + exit.

### Log-Scrubbing
- Pattern-Liste (siehe `24_SECRETS_AND_TOKENS.md`).
- Aktiv in `logging.Filter` + Crash-Handler.

### Telemetrie-Block
- `OLLAMA_NO_TELEMETRY=1`
- `--no-update-check` Flag
- HuggingFace ohne anonymous-stats wenn moeglich

## Verifikation

- Port-Scan von externer IP → kein offener Port
- Whitelist-Bypass-Versuch → Connection-Error
- Zweiter App-Start → erste Instanz vorne, zweite weg
- Logs grep auf Token-Pattern → 0 Treffer
- `pytest tests/test_security/test_llm_security.py -v` gruen
