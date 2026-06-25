# 11 — Backend-Layer (Protocol + Ollama + LM-Studio-Stub)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2 Building-Blocks
> Status: planned · 2026-05-19

## Ziel

Einheitliches Interface fuer alle LLM-Backends. Ollama vollstaendig impl, LM-Studio nur Stub.

## Scope

```python
# services/llm/runtime/base.py
class LlmBackend(Protocol):
    name: str

    def detect_install(self) -> InstallInfo: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_ready(self) -> bool: ...

    def list_local_models(self) -> list[ModelInfo]: ...
    def pull_model(self, id: str, progress_cb) -> None: ...
    def delete_model(self, id: str) -> None: ...

    def chat(self, req: ChatRequest) -> Iterator[ChatChunk]: ...
    def embed(self, req: EmbedRequest) -> EmbedResponse: ...

    # OpenAI-kompatibel
    def openai_base_url(self) -> str: ...
```

- `services/llm/runtime/ollama_embedded.py` — vollstaendige Impl.
- `services/llm/runtime/lmstudio_external.py` — Stub:
  ```python
  class LmStudioExternalBackend:
      def start(self): raise NotImplementedError("LM-Studio-Backend kommt in Folge-Plan")
  ```

## Out of Scope

- Modelfile-Erzeugung — siehe `12_MODELFILE_AND_PARAMS.md`.
- Tool-Calling-Schema — siehe `17_TOOL_CALLING.md`.

## Dependencies

- `httpx` (sync client im Worker-Thread).
- `subprocess` + Windows-Lifecycle (siehe `10_BOOT_AND_LIFECYCLE.md`).

## Offene Klaerungs-Punkte

- [ ] `ChatRequest`/`ChatChunk`-Dataclasses — Schnitt OpenAI-API-style ODER Ollama-native?
  Empfehlung: OpenAI-kompatibel (zukunfts-kompatibel + LM-Studio aktiviert spaeter ohne Caller-Aenderung).
- [ ] Ollama-eigene Endpoints (`/api/chat`) als zusaetzlicher Pfad fuer Funktionen die OpenAI nicht hat?

## Verifikation

- Ollama-Backend integration-test gegen echten Embed-Daemon
- LM-Studio-Stub wirft `NotImplementedError` mit klarer Message
- `pytest tests/test_services/test_llm_backend.py -v` gruen
