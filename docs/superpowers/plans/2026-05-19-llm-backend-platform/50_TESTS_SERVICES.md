# 50 — Tier 4: Service-Coverage-Tests (≥ 85 %)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

Pro Service-Klasse ≥ 85 % Coverage. Pattern wie SCHNITT-Plan A17.

## Scope

- `services/llm/runtime/ollama_embedded.py`
- `services/llm/runtime/lifecycle.py`
- `services/llm/registry.py`
- `services/llm/selector.py`
- `services/llm/modelfile.py`
- `services/llm/downloaders/hf.py`
- `services/llm/downloaders/ollama_pull.py`
- `services/llm/queue.py`
- `services/llm/cache.py`
- `services/llm/embeddings.py`
- `services/llm/tokens.py`
- `services/llm/observability.py`
- `services/llm/tools/registry.py`
- `services/llm/vram_observer.py`
- `services/llm/hardware_probe.py`

## Werkzeuge

- `pytest-cov` + Schwelle pro Modul
- Mock-Backend (siehe Phase 60)
- In-Memory-DB (StaticPool)

## Verifikation

- Coverage-Report ≥ 85 % pro Service
- Keine Regressionen in bestehenden Audio-V2 / Brain V3 Tests
