# 02 — Modell-Registry-Schema

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 1 Foundation
> Status: planned · 2026-05-19

## Ziel

`config/llm_models.json` definiert die Modell-Kandidaten pro Rolle + Score + VRAM-Bedarf + Lizenz. Selector liest das.

## Scope

- JSON-Schema mit Validation (`jsonschema`-Lib).
- Rollen: `reasoner`, `vision`, `omni`, `embeddings`, `reasoning_heavy`.
- Pro Kandidat: `id`, `backend`, `vram_gb`, `quality`, `speed`, `context_max`, `capabilities`, `license_id`, `format`, `experimental`.
- Scoring-Gewichte pro Rolle.
- Registry-Versionierung (`schema_version: "1.0"`).

## Out of Scope

- Inhaltliche Modell-Liste — siehe `03_RESEARCH_MODELS_2026.md`.

## Skizze

```json
{
  "schema_version": "1.0",
  "vram_budget_gb_default": 5.5,
  "roles": {
    "reasoner": {
      "description": "Allgemeines Reasoning / Chat / Tool-Calls",
      "candidates": [
        { "id": "qwen3:8b-q4_K_M", "backend": "ollama",
          "vram_gb": 5.0, "quality": 92, "speed": 70,
          "context_max": 32768, "license_id": "apache-2.0",
          "format": "GGUF", "capabilities": ["chat","tools","json_mode"] }
      ]
    },
    "vision":          { ... },
    "omni":            { ... },
    "embeddings":      { ... },
    "reasoning_heavy": { ... }
  },
  "scoring": {
    "default_weights": { "quality": 0.7, "speed": 0.3 },
    "per_role_weights": {
      "reasoner":        { "quality": 0.65, "speed": 0.35 },
      "vision":          { "quality": 0.75, "speed": 0.25 },
      "omni":            { "quality": 0.80, "speed": 0.20 },
      "embeddings":      { "quality": 0.40, "speed": 0.60 },
      "reasoning_heavy": { "quality": 0.90, "speed": 0.10 }
    }
  },
  "licenses": {
    "apache-2.0":       { "permissive": true,  "url": "https://..." },
    "mit":              { "permissive": true,  "url": "https://..." },
    "llama-community":  { "permissive": false, "url": "https://..." },
    "gemma-terms":      { "permissive": false, "url": "https://..." },
    "openrail-m":       { "permissive": false, "url": "https://..." },
    "cc-by-nc":         { "permissive": false, "url": "https://..." }
  }
}
```

## Offene Klaerungs-Punkte

- [ ] Registry-Update — bei App-Update wird `config/llm_models.json` ueberschrieben. User-Custom-Eintraege per User-Override-File `<app_data>/llm_models.user.json` mergen?
- [ ] Schema-Version-Migration zwischen App-Updates

## Verifikation

- JSON-Schema-Validation pass
- Selector kann Registry laden + sortieren
- `pytest tests/test_services/test_llm_registry.py -v` gruen
