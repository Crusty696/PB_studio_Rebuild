# 60 — Tier 6: Test-Infrastruktur + Mock-Daemon

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

Tests laufen schnell + reproducible, kein echter Ollama-Daemon noetig.

## Scope

- `tests/conftest.py` Erweiterung:
  - Fixture `mock_ollama_server` — kleiner FastAPI/Flask-Server der `/api/tags`, `/api/chat`, `/api/pull`, `/api/embeddings`, `/v1/chat/completions` implementiert mit deterministischen Antworten.
  - Fixture `llm_runtime_fake` — Backend ohne echten Subprozess.
  - Fixture `mock_hf_repo` — gefakter HF-Repo lokal.
  - Fixture `vram_budget_5gb` — pynvml-Mock.
  - Fixture `permissive_license_default` — kein Lizenz-Dialog.
- pytest-Marker:
  - `@pytest.mark.live_llm` — nur bei `--live-llm` Flag (CI skip)
  - `@pytest.mark.long_form` — nur bei `--long-form` Flag

## Verifikation

- Suite laeuft offline ohne echten Daemon
- `pytest tests/test_services/test_llm_*.py -v` gruen ohne `ollama serve`
