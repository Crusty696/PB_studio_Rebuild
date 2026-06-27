# `services/` Layout

Cycle 14 / Option C — Logische Domain-Gruppierung über Aggregator-
`__init__.py`-Indexe. **Keine physischen Moves** — bestehende Caller
bleiben kompatibel.

## Struktur

```
services/
├── audio/                    # Domain-Index für Audio-Services
│   └── __init__.py           # Re-Exports von audio_service, beat_analysis_service, ...
├── video/                    # Domain-Index für Video-Services
│   └── __init__.py
├── agent/                    # Domain-Index für KI-Agent-Services
│   └── __init__.py
├── pacing/                   # Pacing-v2 Pure-Function-Layer (Slice 1-4)
├── graph/                    # D-023 Graph-Knowledge-Stack
├── actions/                  # KI-Action-Handler
├── enrichment/               # Strukturanalyse-Helpers
├── stats/                    # Statistische Helpers
├── memory/                   # Memory-Layer (mem_decision)
└── *.py                      # Top-Level Service-Module (49)
```

## Hinzufügen neuer Services

1. **Klein/eigenständig** → direkt in `services/` als top-level `*.py`
2. **Pacing-Logik** → `services/pacing/`
3. **Graph-Layer** → `services/graph/`
4. **Agent-Hooks** → `services/agent/` (oder direkt)
