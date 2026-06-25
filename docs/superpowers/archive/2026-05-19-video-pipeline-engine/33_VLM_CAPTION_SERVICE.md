# 33 — VLM-Caption-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Pro Keyframe (sparse): Beschreibungs-Caption via VLM. Nutzt Plan-B-Backend.

## Scope

```python
class VlmCaptionService:
    def __init__(self, llm_backend: LlmBackend, prompt_template: str): ...
    def caption_keyframes(self, frames: list[Keyframe]) -> list[Caption]:
        # Pro Frame: base64-encode -> Plan-B Backend "vision"-Rolle -> LLM-Antwort
        ...
```

- Nutzt `services/llm/` (Plan B). Falls Plan B noch nicht fertig:
  - **Stub-Mode:** schreibe Dummy-Captions ("[VLM not yet wired]"), Pipeline laeuft trotzdem durch.
- VLM-Auswahl: Plan-B Auto-Selector waehlt passendes Modell (moondream / minicpm-v / qwen2.5-vl).
- Pro Modell andere Frame-Anzahl pro Batch (Modell-Context-Limit).

## Caching

- Cache via Plan-B Cache-Layer (response-cache).

## Verifikation

- Mit Plan-B-Stub: Pipeline laeuft durch, Dummy-Captions
- Mit Plan-B Backend live: echte Captions
- `pytest tests/test_services/test_vlm_caption.py -v` gruen
