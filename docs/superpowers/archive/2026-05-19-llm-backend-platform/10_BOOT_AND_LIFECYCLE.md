# 10 — Boot + Daemon-Lifecycle

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2 Building-Blocks
> Status: planned · 2026-05-19

## Ziel

Ollama-Embed-Daemon zuverlaessig starten/stoppen pro PB-Studio-Sitzung. Splash haengt nicht. Crash-Recovery.

## Scope

- App-Start-Sequenz:
  1. Single-Instance-Lock pruefen (siehe `72_SECURITY.md`).
  2. Splash anzeigen.
  3. LLM-Runtime asynchron starten (QThread).
  4. UI freischalten — LLM-Status-Dot grau bis ready, dann gruen.
- Daemon-Lifecycle-Manager:
  - `start()`: freien Port holen, ENV setzen, `subprocess.Popen(["ollama.exe","serve"], creationflags=CREATE_NO_WINDOW)`, stdout/stderr in `logs/ollama.log`.
  - `wait_ready()`: HTTP-Poll `/api/tags` mit Timeout.
  - `stop()`: `terminate()` mit 5 s Timeout, dann `kill()`.
  - `restart()`: stop + start + wait_ready.
  - Watchdog-Thread (5 s Poll): wenn Daemon-Crash, Auto-Restart bis max 3 in 60 s.
- PID-File `<app_data>/llm/ollama/pid` mit `pid + port + started_at`.
- Stale-PID-Recovery: beim App-Start pruefen, ob Prozess noch lebt; wenn tot, aufraeumen.
- Sauberer Shutdown via `QApplication.aboutToQuit`.

## Out of Scope

- Health-Gate vor jedem Call — siehe `16_REQUEST_QUEUE_AND_STREAMING.md`.
- Modell-Pull-Flow — siehe `22_DOWNLOADERS_HF_OLLAMA.md`.

## Dependencies

- `pywin32` (optional, fuer Windows-Subprozess-Quirks).
- `socket` fuer freien Port (`bind(("127.0.0.1",0))`).

## Architektur-Skizze

```python
# services/llm/runtime/lifecycle.py
class LlmDaemonLifecycle(QObject):
    state_changed = Signal(str)        # "starting" | "ready" | "stopping" | "crashed"

    def __init__(self, backend: LlmBackend): ...
    def start_async(self) -> None: ...   # QThread
    def stop(self) -> None: ...
    def is_ready(self) -> bool: ...
    def status_dict(self) -> dict: ...   # fuer Status-Dot
```

## Offene Klaerungs-Punkte

- [ ] Daemon **eager** beim App-Start oder **lazy** beim ersten Call?
  Vorschlag: eager + Splash haengt nicht (asynchron, UI freischalten waehrend Boot).
- [ ] Watchdog-Restart-Limit: 3 in 60 s ok oder strenger?
- [ ] Bei `crashed`-State: User-Dialog oder still im Status-Dot?

## Verifikation

- Kalt-Start → ready in < 5 s
- Kill via Task-Manager → Watchdog startet neu, Status-Dot reflektiert
- App-Exit → Daemon stirbt, PID-File entfernt
- `pytest tests/test_services/test_llm_lifecycle.py -v` gruen
