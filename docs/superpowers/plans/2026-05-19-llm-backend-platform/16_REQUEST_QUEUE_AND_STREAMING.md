# 16 — Request-Queue + Streaming

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

LLM-Anfragen geordnet abarbeiten. Streaming-Antworten an UI durchreichen. Cancel mid-stream.

## Scope

- `LlmRequestQueue` (QObject + QThreadPool-Worker).
- Prioritaeten:
  - P0 user-interactive (Chat-Dock)
  - P1 background-analysis (Pacing-Strategist)
  - P2 bulk (Batch-Caption)
- Health-Gate: vor jedem Run pruefen ob Daemon ready.
- VRAM-Gate: Selector + VRAM-Awareness konsultieren.
- Streaming via SSE-Parser:
  - emit `chunk_received(text)`, `done()`, `error(msg)`
- Cancel: `cancel(request_id)` → HTTP-Connection abbrechen, Worker schliesst stream-iterator.
- Per-Request-Timeout (default 120 s, overridable).
- Retry-Backoff: 3 Versuche, Exponential.

## Out of Scope

- Tool-Call-Routing — siehe `17_TOOL_CALLING.md`.

## Skizze

```python
@dataclass
class LlmRequest:
    request_id: str
    role: str
    priority: int
    payload: dict          # OpenAI-style
    stream: bool = True

class LlmRequestQueue(QObject):
    chunk = Signal(str, str)    # (request_id, text)
    done = Signal(str)
    error = Signal(str, str)

    def submit(self, req: LlmRequest) -> None: ...
    def cancel(self, request_id: str) -> None: ...
```

## Verifikation

- Drei P0/P1/P2-Requests gleichzeitig → P0 zuerst geschlossen
- Cancel mid-stream → keine weiteren chunks
- `pytest tests/test_services/test_llm_queue.py -v` gruen
