# Multi-Agenten-System: Architektur-Bericht

**Datum:** 2026-03-19
**Status:** Implementiert & getestet (23/23 Tests bestanden)

---

## Architektur-Überblick

```
User-Input (Chat / Tippfehler erlaubt)
    │
    ▼
┌──────────────────────────────┐
│   LocalAgentService.process()│
│   (Einstiegspunkt)           │
└──────────────┬───────────────┘
               │
    ┌──────────▼──────────┐
    │  OrchestratorAgent   │   ← Zentrale Steuerung
    │  (Phase 1: Routing)  │
    └──┬───┬───┬───┬──────┘
       │   │   │   │
       ▼   ▼   ▼   ▼
   ┌─────┐ ┌─────┐ ┌──────┐ ┌───────────────┐
   │Audio│ │Vision│ │Editor│ │ActionRegistry  │
   │Agent│ │Agent │ │Agent │ │(Fuzzy-Matching)│
   └─────┘ └─────┘ └──────┘ └───────────────┘
       │       │       │            │
       └───────┴───────┴────────────┘
                    │
            ┌───────▼────────┐
            │  ModelManager   │  ← Nur 1 Modell im RAM/VRAM
            │  (Ressourcen-   │
            │   Schutz)       │
            └────────────────┘
```

---

## Sektor 1: Fuzzy-Matching (ActionRegistry)

**Datei:** `services/action_registry.py`

### Neue Methoden:
- `fuzzy_match(name)` → Findet die ähnlichste Aktion per `thefuzz.fuzz.token_sort_ratio`
- `resolve(name)` → Löst ungenaue Namen auf (exakt → fuzzy → None)
- `execute()` → Nutzt jetzt `resolve()` + tolerante Parameter (unbekannte Keys werden entfernt)

### Fuzzy-Beispiele (getestet):
| Eingabe (fehlerhaft) | Aufgelöst zu | Score |
|---|---|---|
| `analyse_files` | `analyze_audio` | 65%+ |
| `analyz_audio` | `analyze_audio` | 85%+ |
| `seperate_stems` | `separate_stems` | 90%+ |
| `export_timelien` | `export_timeline` | 80%+ |
| `xyzqwerty_foobar` | None (abgelehnt) | <55% |

### Tolerante Parameter:
Unbekannte Parameter werden **still entfernt** statt einen TypeError zu werfen.
Beispiel: `execute("analyze_audio", {"track_id": 1, "unknown": "junk"})` → funktioniert.

---

## Sektor 2: Multi-Agenten-Architektur

**Ordner:** `agents/`

### Klassen-Hierarchie:
```
BaseAgent (ABC)
├── VisionAgent   → Video/Bild-Analyse (analyze_video)
├── AudioAgent    → Audio-Analyse (analyze_audio, separate_stems)
├── EditorAgent   → Timeline/Export (auto_edit, export_timeline)
└── OrchestratorAgent → Routing-Zentrale
```

### Routing-Logik (OrchestratorAgent):
1. **"Analysiere alle"** → Spezialbehandlung: Holt ALLE importierten IDs aus DB, führt `analyze_audio` + `analyze_video` für jeden Eintrag aus
2. **Keyword-Scoring** → Jeder Agent hat `can_handle(text) → float`. Höchster Score gewinnt (min. 0.3)
3. **Registry-Fuzzy** → Direktes Fuzzy-Matching auf Aktionsnamen im Text
4. **LLM-Fallback** → Text-Modell generiert JSON-Antwort (mit Fuzzy-Korrektur)

### Keyword-Listen:
- **AudioAgent:** audio, musik, beat, bpm, stem, vocals, drums, bass, track...
- **VisionAgent:** video, clip, szene, bild, frame, kamera, auflösung...
- **EditorAgent:** edit, schnitt, timeline, export, render, import...

---

## Sektor 3: Ressourcen-Schutz (ModelManager)

**Datei:** `services/local_agent_service.py`

### Klasse: `ModelManager`
- **Regel:** Nur 1 Modell gleichzeitig im RAM/VRAM
- `load(model_id)` → Entlädt vorheriges Modell automatisch, lädt neues
- `unload()` → Gibt RAM/VRAM frei, leert CUDA-Cache
- `ensure_loaded(model_id)` → Alias für load()

### Integration:
- `LocalAgentService` nutzt `ModelManager` statt eigenes Laden/Entladen
- `OrchestratorAgent` erhält Referenz auf `ModelManager` per `set_model_manager()`
- Wenn ein Agent ein eigenes Modell braucht (z.B. CLIP für Vision), ruft der Orchestrator `model_manager.ensure_loaded(agent.model_id)` → Text-Modell wird automatisch entladen

---

## Sektor 4: Tippfehler-Simulation

**Eingabe:** `"analysiere alle File die improtiert sind"`

### Ablauf:
1. Orchestrator erkennt per Fuzzy (token_sort_ratio > 60%) dass dies "analysiere alle importierten Dateien" bedeutet
2. `_handle_analyze_all()` wird aufgerufen
3. Alle AudioTrack-IDs → `analyze_audio(track_id=X)`
4. Alle VideoClip-IDs → `analyze_video(clip_id=X)`
5. Multi-Action-Ergebnis wird zurückgegeben

### Test-Ergebnis: BESTANDEN

---

## Dateien (neu/geändert)

| Datei | Status | Zweck |
|---|---|---|
| `agents/__init__.py` | NEU | Package-Init |
| `agents/base_agent.py` | NEU | Abstrakte Basisklasse |
| `agents/orchestrator_agent.py` | NEU | Zentrale Routing-Logik |
| `agents/vision_agent.py` | NEU | Video/Bild-Spezialist |
| `agents/audio_agent.py` | NEU | Audio-Spezialist |
| `agents/editor_agent.py` | NEU | Timeline/Export-Spezialist |
| `services/action_registry.py` | GEÄNDERT | +Fuzzy-Matching, +tolerante Params |
| `services/local_agent_service.py` | GEÄNDERT | +ModelManager, +Orchestrator-Integration |
| `tests/test_multi_agent.py` | NEU | 23 Tests (alle bestanden) |
| `pyproject.toml` | GEÄNDERT | +thefuzz Dependency |

---

## Nächste Schritte (Empfehlung)

1. **Vision-Modell** (CLIP/BLIP) im VisionAgent integrieren → ModelManager swappt automatisch
2. **Kontext-Propagation** → Session-IDs und Projekt-Kontext durch die Agent-Kette leiten
3. **Agent-Memory** → Kurzzeitgedächtnis für Multi-Turn-Dialoge
4. **Parallele Agenten** → Mehrere Agenten gleichzeitig befragen, bestes Ergebnis wählen
