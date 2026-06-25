# 32 — Settings-Dialog LLM-Sektion

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 3 UI
> Status: planned · 2026-05-19

## Ziel

Zentrale Steuerstelle fuer alle LLM-Einstellungen.

## Scope

```
Settings ▸ LLM
├── Backend
│     ◉ Ollama (embedded)
│     ○ LM Studio (extern, falls installiert)   [grau, Folge-Plan]
├── Modell-Rollen
│     Reasoner:    [qwen3:8b-q4 ▼]   [Pin]  [Manager]
│     Vision:      [minicpm-v:8b ▼]  [Pin]  [Manager]
│     Omni:        [— keiner — ▼]    [Pin]  [Manager]
│     Embeddings:  [bge-m3 ▼]                [Manager]
│     Reasoning-Heavy: [deepseek-r1:8b ▼]    [Manager]
├── HuggingFace
│     Token: [hf_••••]  [Test] [Loeschen]
│     Status: ✓ Account: davidlochmann2
├── Storage
│     Pfad: C:\Users\…\PBStudio\llm\        [Aendern]
│     Belegt: 12.3 GB / 480 GB frei
│     [Cleanup-Tool]
├── Auto-Vorschlaege
│     ☑ Bessere Modelle vorschlagen
│     ☐ Nicht mehr fragen fuer Vision
├── Diagnose
│     LLM-Status: ✓ ready  Port 11435
│     [Daemon neu starten]   [Logs oeffnen]
```

## Verifikation

- Backend-Wechsel Stub bleibt grau + Tooltip "Folge-Plan"
- Hot-Reload-Modell-Wechsel ohne Neustart
- `pytest tests/test_ui/test_settings_llm.py -v` gruen
