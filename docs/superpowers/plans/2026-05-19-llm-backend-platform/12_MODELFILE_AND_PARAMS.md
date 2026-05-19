# 12 — Modelfile-Generator + Parameter

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Pro Modell + Rolle ein passendes Ollama-Modelfile erzeugen. Korrekte Chat-Templates + Default-Parameter.

## Scope

- Modelfile-Templates pro Familie (Llama, Qwen, Phi, Gemma, etc.). Chat-Template-Strings.
- Default-PARAMETER pro Rolle:
  - `reasoner`         → temperature 0.7, top_p 0.9, num_ctx role-spezifisch
  - `vision`           → temperature 0.2 (faktisch), top_p 0.9
  - `omni`             → temperature 0.3
  - `embeddings`       → keine (Modus = embed)
  - `reasoning_heavy`  → temperature 0.6, num_predict gross
- SYSTEM-Prompt pro Rolle (Deutsch-Pflicht falls Sprache-Setting Deutsch).
- Generator schreibt temp-Modelfile, ruft `ollama create <local_name> -f Modelfile` ab, cleanup.

## Out of Scope

- VLM-Image-Encoding (siehe `77_MULTIMODAL_PLUMBING.md`).

## Skizze

```python
# services/llm/modelfile.py
def render_modelfile(gguf_path: Path, family: str, role: str, lang: str) -> str:
    template = CHAT_TEMPLATES[family]
    sys_prompt = SYSTEM_PROMPTS[role][lang]
    params = ROLE_PARAMS[role]
    return f"""FROM {gguf_path}
TEMPLATE \"\"\"{template}\"\"\"
SYSTEM \"\"\"{sys_prompt}\"\"\"
{params_to_modelfile(params)}
"""
```

## Offene Klaerungs-Punkte

- [ ] SYSTEM-Prompts pro Rolle inhaltlich festlegen — abgestimmt mit PB-Studio-Anwendung
- [ ] num_ctx pro Modell aus Registry vs Hard-Coded
- [ ] Sprache-Erzwingung: ueberhaupt im SYSTEM-Prompt oder per-Request?

## Verifikation

- Modelfile syntaktisch korrekt (`ollama create` ohne Fehler)
- Chat-Output respektiert SYSTEM-Prompt-Sprache
- `pytest tests/test_services/test_llm_modelfile.py -v` gruen
