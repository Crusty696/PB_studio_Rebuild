# 22 — Downloaders (HuggingFace + Ollama-Hub)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Modelle direkt aus PB Studio laden, mit Progress-UI + Cancel + Resume.

## Scope

```python
# services/llm/downloaders/base.py
class ModelDownloader(Protocol):
    def estimate_size(self, id: str) -> int: ...
    def download(self, id: str, target: Path, progress_cb, cancel_token) -> Path: ...
```

- **ollama_pull** — `POST /api/pull` mit SSE-Progress, native fuer Ollama-Hub-IDs.
- **hf** — `huggingface_hub`-Lib mit:
  - resumable downloads
  - HF-Token aus Keyring (siehe `24_SECRETS_AND_TOKENS.md`)
  - target: `<app_data>/llm/staging/<repo>/<file.gguf>`
  - Nach Download: `gguf_to_ollama.py` Installer (Modelfile + `ollama create <local_name>`)
- Disk-Space-Probe vor Download (siehe `23_STORAGE_MANAGEMENT_MODELS.md`).
- SHA256-Verify nach Download (falls Quelle liefert).
- Network-Retry mit Backoff.

## Out of Scope

- CivitAI (out of scope laut User-Entscheidung).

## Verifikation

- Cancel mitten im Download → partial file cleanup
- Resume nach Cancel → weiter ab Offset
- HF mit Token gegen Public-Repo
- `pytest tests/test_services/test_llm_downloaders.py -v` gruen
