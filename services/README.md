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

## Migration-Empfehlung

**Neue Caller** sollten die Domain-Indexe nutzen:

```python
# Empfohlen — gruppiert
from services.audio import (
    AudioAnalyzer, BeatAnalysisService, DEFAULT_SR,
)
from services.video import VideoAnalyzer, VectorDBService
from services.agent import LocalAgentService, ActionRegistry
```

**Bestehende Imports bleiben unverändert kompatibel:**

```python
# Funktioniert weiterhin
from services.audio_service import AudioAnalyzer
from services.beat_analysis_service import BeatAnalysisService
```

## Domain-Mapping

| Domain | Public-API | Quelldateien |
|---|---|---|
| `services.audio` | AudioAnalyzer, BeatAnalysisService, OnsetRhythmService, StructureDetectionService, DEFAULT_SR, HOP_LENGTH | audio_service.py, beat_analysis_service.py, onset_rhythm_service.py, structure_detection_service.py, audio_constants.py |
| `services.video` | VideoAnalyzer, SceneInfo, detect_scenes, generate_embeddings, text_to_embedding, VectorDBService | video_service.py, video_analysis_service.py, vector_db_service.py |
| `services.agent` | ActionRegistry, action_registry, LocalAgentService, OllamaClient | action_registry.py, local_agent_service.py, ollama_client.py |
| `services.pacing` | (siehe `services/pacing/__init__.py`) | services/pacing/* |
| `services.graph` | (siehe `services/graph/__init__.py`) | services/graph/* |

## Hinzufügen neuer Services

1. **Klein/eigenständig** → direkt in `services/` als top-level `*.py`
2. **Pacing-Logik** → `services/pacing/`
3. **Graph-Layer** → `services/graph/`
4. **Agent-Hooks** → `services/agent/` (oder direkt + Re-Export ergänzen)

Die Domain-`__init__.py`-Re-Exports sollten beim Hinzufügen neuer
Public-API erweitert werden, damit der Aggregator-Import-Pfad
gepflegt bleibt.
