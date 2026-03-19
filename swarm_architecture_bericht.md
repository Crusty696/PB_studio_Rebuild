# PB Studio — 3-Agenten Swarm Architektur-Bericht

**Datum:** 2026-03-19
**Version:** 0.4.0 (Swarm Update)
**Status:** Implementiert & Integriert

---

## 1. Übersicht

Das PB Studio Multi-Agenten-System besteht aus drei spezialisierten KI-Agenten,
die von einem zentralen Orchestrator koordiniert werden. Alle Agenten laufen
**100% offline** auf der lokalen Hardware (CPU/GPU).

```
┌─────────────────────────────────────────────────────────┐
│                    USER INPUT (Chat)                     │
│                  "Analysiere Bild und Ton"               │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              ORCHESTRATOR AGENT (Das Gehirn)             │
│                                                          │
│  Routing-Pipeline:                                       │
│  1. "Analysiere alle" → Batch-Analyse                   │
│  2. Multi-Step Detection → Vision + Audio parallel       │
│  3. Specialized Agent Routing (can_handle Score)         │
│  4. Fuzzy Action Registry                                │
│  5. LLM Fallback (Qwen2.5-0.5B)                        │
└──────┬──────────────┬──────────────┬────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ VISION     │ │ AUDIO      │ │ EDITOR     │
│ AGENT      │ │ AGENT      │ │ AGENT      │
│ (Das Auge) │ │ (Das Ohr)  │ │ (Die Hand) │
│            │ │            │ │            │
│ Moondream2 │ │ Whisper    │ │ Registry   │
│ OpenCV     │ │ faster-    │ │ Actions    │
│            │ │ whisper    │ │            │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │
      └──────────────┴──────────────┘
                     │
                     ▼
      ┌──────────────────────────────┐
      │    SINGLETON MODEL MANAGER    │
      │   (Striktes VRAM-Management) │
      │                              │
      │  REGEL: Max 1 Modell im RAM  │
      │  Auto-Swap + gc.collect()    │
      │  + torch.cuda.empty_cache()  │
      └──────────────────────────────┘
```

---

## 2. Komponenten im Detail

### 2.1 ModelManager (`services/model_manager.py`)

**Typ:** Singleton (Thread-safe via `threading.Lock`)

**Verantwortung:** Striktes RAM/VRAM-Management. Stellt sicher, dass **immer nur
EIN KI-Modell** gleichzeitig im Speicher liegt.

**Modell-Typen:**
| Typ | Methode | Verwendung |
|-----|---------|------------|
| `transformers` | `load_transformers()` | Qwen2.5-0.5B (Text-LLM) |
| `whisper` | `load_whisper()` | faster-whisper (Transkription) |
| `vision` | `load_vision()` | Moondream2 (Bildanalyse) |

**Swap-Mechanismus:**
```python
# Automatischer Swap: Wenn Vision geladen wird, wird Whisper entladen
mm = ModelManager()  # Singleton
mm.load_whisper("base")      # Whisper geladen
mm.load_vision("moondream2") # → Whisper entladen → Vision geladen
```

**Speicher-Bereinigung bei Swap:**
1. Alle Python-Referenzen auf `None` setzen
2. `gc.collect()` — Python Garbage Collector
3. `torch.cuda.empty_cache()` — CUDA-Cache leeren
4. `torch.cuda.synchronize()` — Auf GPU-Abschluss warten

### 2.2 Audio-Agent (`agents/audio_agent.py`)

**Modell:** faster-whisper (Größe: `base`, ~140MB)
**Device:** CPU (`int8`) oder CUDA (`float16`)

**Fähigkeiten:**
- `transcribe_audio` — Spracherkennung mit Zeitstempeln
- `analyze_audio` — BPM, Beats, Energiekurve (librosa)
- `separate_stems` — Stem-Separation (Demucs)

**Transkriptions-Erkennung (Keywords):**
```
transkri*, transcri*, speech, sprache, gesagt,
was wird gesagt, untertitel, subtitle, whisper
```

**Output-Format:**
```json
{
    "language": "de",
    "language_probability": 0.95,
    "duration": 120.5,
    "segments": [
        {"start": 0.0, "end": 3.5, "text": "Hallo und willkommen..."}
    ],
    "full_text": "Hallo und willkommen...",
    "segment_count": 42
}
```

**Sicherheit:**
- Prüft via `ffprobe` ob die Datei eine Audio-Spur hat
- Videos ohne Audio werden sofort mit Fehlermeldung zurückgegeben
- VAD-Filter aktiviert (Voice Activity Detection)

### 2.3 Vision-Agent (`agents/vision_agent.py`)

**Modell:** Moondream2 (`vikhyatk/moondream2`, ~1.8GB)
**Device:** CPU (`float32`) oder CUDA (`float16`)

**Fähigkeiten:**
- `analyze_video_content` — KI-basierte Szenenanalyse
- `analyze_video` — Metadaten via FFprobe (bestehend)

**Frame-Extraktion (OpenCV):**
1. Video öffnen mit `cv2.VideoCapture`
2. Alle X Sekunden ein Frame extrahieren (`interval_sec`, default: 5s)
3. BGR → RGB → PIL Image konvertieren
4. Maximal N Frames analysieren (`max_frames`, default: 10)

**KI-Analyse (Moondream2):**
1. Frame als PIL Image an `model.encode_image()` übergeben
2. Prompt: "Describe this image in detail. What is happening in the scene?"
3. Antwort via `model.answer_question()` generieren

**Output-Format:**
```json
{
    "file_path": "C:/path/to/video.mp4",
    "duration_sec": 30.0,
    "fps": 30.0,
    "total_frames_analyzed": 5,
    "interval_sec": 5.0,
    "scenes": [
        {
            "frame_index": 0,
            "timestamp_sec": 0.0,
            "description": "A dark forest illuminated by bioluminescent plants..."
        }
    ],
    "summary": "5 Szenen aus 30.0s Video analysiert."
}
```

### 2.4 Orchestrator-Agent (`agents/orchestrator_agent.py`)

**Routing-Pipeline (5 Stufen):**

| Priorität | Erkennung | Aktion |
|-----------|-----------|--------|
| 1 | "Analysiere alle importierten" | Batch: alle Audio+Video |
| 2 | Bild+Ton Keywords gleichzeitig | Multi-Step: Vision → Audio → Zusammenfassung |
| 3 | Agent `can_handle()` Score ≥ 0.3 | Weiterleitung an spezialisierten Agent |
| 4 | Fuzzy-Match auf Action-Registry | Direkte Aktion ausführen |
| 5 | Kein Match | LLM-Fallback (Qwen2.5) |

**Multi-Step-Erkennung:**
```
Keyword-Paare: (bild, ton), (video, audio), (sehen, gesagt),
               (passiert, gesagt), (visuell, akustisch)
Direkte: "bild und ton", "video und audio"
```

**Multi-Step-Ablauf:**
```
User: "Was passiert in Video 1 und was wird gesagt?"
  │
  ├─ Schritt 1: Vision-Agent → Moondream2 Szenen-Analyse
  │   └─ ModelManager: load_vision("moondream2")
  │
  ├─ Schritt 2: Audio-Agent → faster-whisper Transkription
  │   └─ ModelManager: unload Vision → load_whisper("base")
  │
  └─ Schritt 3: Zusammenfassung im Chat:
       🎬 VISUELLE ANALYSE (3 Szenen):
         [0.0s] A gothic figure standing in a bioluminescent jungle...
         [5.0s] Camera pans through glowing mushrooms...
       🎤 TRANSKRIPTION (Sprache: en):
         Welcome to the enchanted forest...
```

---

## 3. Action Registry — Neue Aktionen

| Aktion | Agent | Beschreibung |
|--------|-------|-------------|
| `transcribe_audio` | Audio | Spracherkennung (faster-whisper) |
| `analyze_video_content` | Vision | KI-Szenenanalyse (Moondream2) |
| `analyze_audio` | Audio | BPM/Beats/Energie (librosa) |
| `analyze_video` | Vision | Metadaten (FFprobe) |
| `separate_stems` | Audio | Stem-Separation (Demucs) |
| `auto_edit` | Editor | Beat-synchrone Timeline |
| `import_file` | Editor | Datei-Import |
| `export_timeline` | Editor | Video-Export (FFmpeg) |
| `list_actions` | System | Alle Aktionen anzeigen |

---

## 4. Dependencies

### Neue Abhängigkeiten (Swarm Update):
```toml
faster-whisper = ">=1.2.1"   # Offline Speech-to-Text
einops = ">=0.8.2"           # Tensor-Operationen (Moondream2)
pillow = ">=12.1.1"          # Bildverarbeitung
```

### Bestehende (relevant):
```toml
transformers = ">=5.3.0"     # HuggingFace (LLM + Vision)
torch = ">=2.10.0"           # PyTorch
opencv-python = ">=4.13.0"   # Frame-Extraktion
```

---

## 5. VRAM-Budget (GTX 1060 6GB)

| Modell | VRAM (float16) | RAM (float32) |
|--------|---------------|---------------|
| Qwen2.5-0.5B | ~1.0 GB | ~2.0 GB |
| faster-whisper base | ~0.5 GB | ~0.3 GB (int8) |
| Moondream2 | ~3.5 GB | ~3.5 GB |
| **Max gleichzeitig** | **~3.5 GB** | **~3.5 GB** |

**Sicherheitsmarge:** ~2.5 GB VRAM frei für System + OS

---

## 6. Threading & GUI-Integration

```
┌────────────────────────┐
│     MainWindow (GUI)    │
│                         │
│  ┌─────────────────┐   │
│  │   ChatDock       │   │
│  │                  │   │
│  │  Input → Worker  │──────┐
│  │  ⏳ "KI denkt..."│   │  │
│  │  ← Ergebnis      │◄─┤  │
│  └─────────────────┘   │  │
└────────────────────────┘  │
                            │
                     ┌──────┴──────┐
                     │  QThread    │
                     │             │
                     │ AIAgent     │
                     │ Worker      │
                     │             │
                     │ agent.      │
                     │ process()   │
                     └─────────────┘
```

- `AIAgentWorker` (QObject) läuft in separatem `QThread`
- GUI bleibt responsive während Modell-Download und Inferenz
- `finished` Signal → Ergebnis im Chat anzeigen
- `error` Signal → Fehlermeldung im Chat
- Input-Feld wird während Verarbeitung gesperrt

---

## 7. Dateien (erstellt/modifiziert)

### Neue Dateien:
| Datei | Zweck |
|-------|-------|
| `services/model_manager.py` | Singleton VRAM Manager |
| `tests/test_swarm_integration.py` | Integrations-Tests |
| `tests/test_unit_swarm.py` | Unit-Tests (ohne ML) |
| `tests/run_full_swarm_test.py` | Full E2E Test |
| `swarm_architecture_bericht.md` | Dieser Bericht |

### Modifizierte Dateien:
| Datei | Änderung |
|-------|----------|
| `agents/audio_agent.py` | Transkriptions-Erkennung + Routing |
| `agents/vision_agent.py` | KI-Inhaltsanalyse (Moondream2) |
| `agents/orchestrator_agent.py` | Multi-Step-Analyse (Vision+Audio) |
| `services/local_agent_service.py` | Singleton ModelManager Integration |
| `services/register_actions.py` | `transcribe_audio` + `analyze_video_content` |
| `pyproject.toml` | faster-whisper, einops, pillow |

---

## 8. Self-Healing Mechanismen

1. **Audio-Stream-Check:** Videos ohne Audio-Spur werden vor Whisper-Aufruf
   erkannt → sofortige Fehlermeldung statt Endlos-Hänger

2. **ModelManager Auto-Swap:** Wenn ein Agent ein anderes Modell braucht,
   wird das aktuelle automatisch entladen → kein manuelles Memory-Management

3. **GC + CUDA Cleanup:** Nach jedem Modell-Entladen wird aggressiv aufgeräumt
   (gc.collect + cuda.empty_cache + cuda.synchronize)

4. **Graceful Degradation:** Wenn CUDA nicht verfügbar → automatischer CPU-Fallback
   mit angepasstem compute_type (float16 → int8)

5. **Fuzzy Action Matching:** Tippfehler in Aktionsnamen werden automatisch
   korrigiert (Schwellwert: 55%)

---

## 9. Test-Ergebnisse

### Unit-Tests (pytest): 30/30 bestanden
```
tests/test_multi_agent.py ........ 23 passed
tests/test_action_registry.py ... 7 passed
```

### Swarm Integration-Tests: 7/7 bestanden
```
PASS audio_stream_check        — Videos ohne Audio korrekt erkannt
PASS whisper_transcription      — faster-whisper auf 8s Video (5.6s)
PASS vision_analysis            — OpenCV-Analyse auf CPU (0.2s)
PASS model_swap                 — Whisper korrekt geladen nach Vision
PASS model_unload               — Modell korrekt entladen
PASS multi_step_detection       — "Bild und Ton" erkannt
PASS agent_routing              — Audio/Vision-Agent korrekt geroutet
```

---

## 10. Bekannte Limitierungen & Self-Healing

1. **Moondream2 nur auf GPU:** Auf CPU dauert `encode_image` ~400s pro Frame
   (1.8B Parameter in float32). **Self-Healing:** Automatischer Fallback auf
   OpenCV-basierte Bildanalyse (Helligkeit, Farbton, Kantenkomplexität) in <1s.

2. **Sequenziell, nicht parallel:** Vision und Audio laufen nacheinander
   (ModelManager erlaubt nur 1 Modell). Auf GPU: ~20s total für beide.

3. **Moondream2 Download:** Erster Start erfordert ~1.8 GB Download von
   HuggingFace. Danach gecacht.

4. **Sora-Videos:** Die meisten generierten Videos haben keine Audio-Spur.
   **Self-Healing:** ffprobe-Check vor Whisper-Aufruf, sofortige Fehlermeldung.

5. **Deadlock-Fix:** `threading.RLock()` statt `Lock()` im ModelManager,
   damit `load_*()` → `unload()` kein Deadlock verursacht.

6. **Whisper-Modellgröße:** Konfigurierbar via `PB_WHISPER_SIZE` Environment-Variable
   (default: "tiny"). Für Produktion: "base" oder "small" empfohlen.
