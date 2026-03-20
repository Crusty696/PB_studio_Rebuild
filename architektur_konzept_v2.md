# PB Studio Rebuild — Architektur-Konzept v2.0

**Datum:** 2026-03-20
**Status:** Machbarkeits- und Architektur-Recherche
**Ziel:** Moderne 2026-Standards evaluieren, bevor Prototyp-Konzepte blind uebernommen werden

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Prototyp-Analyse: Was existiert](#2-prototyp-analyse-was-existiert)
3. [Timeline & Anchors: OpenTimelineIO](#3-timeline--anchors-opentimelineio)
4. [Video-Analyse & Suche: Vector-DB Vergleich](#4-video-analyse--suche-vector-db-vergleich)
5. [Audio DJ-Engine: Beat/Downbeat-Tracking](#5-audio-dj-engine-beatdownbeat-tracking)
6. [Konvertierung/Proxies: FFmpeg NVENC](#6-konvertierungproxies-ffmpeg-nvenc)
7. [Gesamtarchitektur-Empfehlung](#7-gesamtarchitektur-empfehlung)
8. [Implementierungs-Roadmap](#8-implementierungs-roadmap)

---

## 1. Executive Summary

PB Studio ist eine lokale PySide6 Desktop-App fuer DJ-Set Videoproduktion. Sie analysiert Audio (BPM, Beats, Struktur), versteht Video semantisch (Szenen, Motion, Embeddings) und generiert beat-synchrone Timelines automatisch.

**Kernentscheidungen dieses Whitepapers:**

| Bereich | Empfehlung | Grund |
|---------|------------|-------|
| Timeline-Backend | **OpenTimelineIO** | Industrie-Standard, DaVinci-Export, Marker fuer Anchors |
| Vector-Suche | **LanceDB** (statt ChromaDB/SQLite) | Embedded, schneller, weniger RAM, built-in CLIP |
| Audio-Analyse | **librosa + beat_this** (statt madmom) | Windows-kompatibel, GPU-beschleunigt, Python 3.11+ |
| Proxy/Konvertierung | **FFmpeg subprocess + NVENC** | 5-10x schneller, GTX 1060 unterstuetzt |

---

## 2. Prototyp-Analyse: Was existiert

### 2.1 Python-Prototyp (Version B / Nvidia)

**5-Schritt-Pipeline:**

| Schritt | Aufgabe | Technologie | Ergebnis |
|---------|---------|-------------|----------|
| 0 | Proxy-Erstellung | FFmpeg | Downsampled MP4s in `cache/proxies/` |
| 1 | Scene Detection | PySceneDetect (ContentDetector, threshold=27) | Shot-Grenzen in DB |
| 2 | Motion Analysis | RAFT Optical Flow (PyTorch) | Motion-Profile pro Frame-Paar |
| 3 | Captioning | Moondream2 (vikhyatk/moondream2) | Natuerlichsprachliche Szenenbeschreibung |
| 4 | Embeddings | SigLIP so400m (1152-dim) | Semantische Vektoren in SQLiteVectorStore |

**Anchor-System:**
- `AnchorData`-Dataclass: audio_start/end, audio_features (20-dim), video_embedding (1152-dim SigLIP), label
- Audio-Features: 8-Band Spektral (sub bis air) + Energy-Stats + Beat-Dichte = 20 Dimensionen
- Matching: Cosine-Similarity > 0.5 → Anchor-Video-Praeferenz wird gewichtet (0.7-0.9)
- Zweck: Few-Shot-Learning — User zeigt dem System, welche Videos zu welcher Musik passen

**Pacing-Engine:**
- Input: Audio-Pfad + verfuegbare Video-Clips
- Analyse: BPM (BeatNet/madmom/librosa), Beat-Grid, Song-Struktur (Intro/Verse/Chorus/Drop), Spektral (8-Band)
- Cut-Generierung: Trigger-Punkte (beats, onsets, kicks, snares, hi-hats, energy peaks) mit Staerke-Score (0.0-1.0)
- Clip-Selektion: random, round_robin, motion-matching, semantic (CLIP-basiert)
- Key-Konstanten: HARD_CUT_THRESHOLD=0.7, MIN_DURATION_DROP=0.3s, MIN_DURATION_BUILDUP=1.0s
- GPU-Management: Mutex-basiert, max 4000MB VRAM (GTX 1060)

**Datenbank:** SQLite + SQLAlchemy + DuckDB (Analytics) + SQLiteVectorStore

### 2.2 C#-Prototyp (WPF / .NET 9.0)

**Architektur:** Hybrid C#-Python ueber ZeroMQ Dual-Channel IPC
- Channel A (REQ/REP Port 5570): Synchrone Befehle
- Channel B (PUB/SUB Port 5571): Asynchrone Datenstreams
- IpcMessageBus: Batcht eingehende Nachrichten (33ms / ~30 FPS)

**Anchor-System (erweitert):**
```
AudioVideoAnchorModel
├─ BeatPosition     — Fester Beat-Index ("bei Beat 64")
├─ AudioTimestamp   — Zeitstempel (Sekunden)
├─ SceneId          — Verknuepfte Video-Szene
├─ FeatureVectorJson — 20-dim Feature-Vektor (SigLIP)
└─ Label            — User-Annotation
```
- Visueller Editor mit Waveform-Hintergrund (AnchorEditorWidget)
- Drag-Create/Resize auf Timeline
- Farbkodierte Regionen (6-Farben-Rotation)

**Pacing-Engine (erweitert):**
- 10 konfigurierbare Gewichte: BeatWeight, KickWeight, SnareWeight, HiHatWeight, OnsetWeight, EnergyWeight, EnergyThreshold, MinCutInterval, MaxCutInterval, Variation
- Zwei Modi: Classic (beat-basiert) und Smart (CLAP mood-aware)
- SpeedTarget: 2-10s durchschnittliche Clip-Dauer

**Timeline:** Frame-basiert (60 FPS fest), Timecode-Arithmetik, Clip-Virtualisierung, Multi-Track

**Playback-Engine:** NAudio (Master-Clock) + FFmpeg-Subprocess (Frame-Decoder) + CompositionTarget.Rendering (~60 FPS)

### 2.3 Aktueller Rebuild (v0.4.0)

**Status:** 31/104 Features implementiert (29.8%)
- 3-Agenten KI-Swarm (Vision/Audio/Editor + Orchestrator)
- ModelManager Singleton fuer VRAM-Management
- PySide6 GUI mit 4 Workspaces (Media/Edit/Convert/Deliver)
- Pacing-Service mit Beat-Grid-basiertem Auto-Edit
- 4 kritische Bugs identifiziert (siehe GRAND_AUDIT_REPORT.md)

**Hauptproblem des Rebuilds:** Viel Code, aber die Kern-Pipeline (5-Schritt Video-Analyse, Anchor-Matching, Smart-Director) fehlt noch komplett.

---

## 3. Timeline & Anchors: OpenTimelineIO

### 3.1 Altes Problem

- Timeline ist als einfache `List[TimelineClip]` / JSON-Blob gespeichert
- Kein Industrie-Standard-Format → kein Export zu DaVinci Resolve
- Anchors sind proprietaere Datenstruktur ohne Interoperabilitaet
- Keine Transitions, keine Nested-Compositions, keine Multi-Track-Logik im Backend

### 3.2 Neue Loesungsvorschlaege

**OpenTimelineIO (OTIO) als Timeline-Backend:**

| Feature | OTIO-Support | Bewertung |
|---------|-------------|-----------|
| Clips mit In/Out-Points | Ja | Direkte Abbildung auf `otio.schema.Clip` |
| Multi-Track (Video + Audio) | Ja | `otio.schema.Stack` mit beliebig vielen `Track`s |
| Transitions (Crossfade) | Ja | `otio.schema.Transition` mit duration |
| Markers / Anchors | Ja | `otio.schema.Marker` mit time_range + metadata dict |
| Beat-Grid Speicherung | Via Metadata | Beats als JSON-Array in Track/Clip Metadata |
| DaVinci Resolve Export | Ja (EDL/FCP XML) | CMX 3600 EDL = zuverlaessigster Pfad |
| Python API | Stabil (v0.18.1) | `pip install OpenTimelineIO` |
| PySide6 Kompatibilitaet | Kein Konflikt | OTIO hat keine UI-Abhaengigkeit |

**Anchor-Abbildung auf OTIO-Marker:**
```python
import opentimelineio as otio

anchor_marker = otio.schema.Marker(
    name="Drop Anchor - Laser Show",
    marked_range=otio.opentime.TimeRange(
        start_time=otio.opentime.RationalTime(128, 1),  # Beat 128
        duration=otio.opentime.RationalTime(32, 1)       # 32 Beats lang
    ),
    color=otio.schema.MarkerColor.RED,
    metadata={
        "pb_studio": {
            "type": "anchor",
            "audio_features": [0.8, 0.3, ...],  # 20-dim
            "video_embedding": [0.12, -0.45, ...],  # 1152-dim (Referenz in LanceDB)
            "similarity_threshold": 0.5,
            "blend_weight": 0.85
        }
    }
)
```

**Export-Workflow:**
```
PB Studio Timeline (OTIO intern)
    → otio.adapters.write_to_file("export.edl", timeline, adapter_name="cmx_3600")
    → DaVinci Resolve: File → Import → EDL
```

### 3.3 Python Library Empfehlung

| Library | Version | Zweck |
|---------|---------|-------|
| `opentimelineio` | 0.18.1 | Timeline-Datenmodell + EDL/FCP Export |
| `otio-fcp-adapter` | 0.3.0 | FCP 7 XML Export (Alternative zu EDL) |

### 3.4 Implementierungs-Aufwand

| Task | Aufwand | Abhaengigkeit |
|------|---------|---------------|
| OTIO als Timeline-Backend integrieren | **Mittel** (2-3 Tage) | Ersetzt `List[TimelineClip]` |
| Anchor-System auf OTIO-Marker migrieren | **Gering** (1 Tag) | Metadata-Dict statt eigener Klasse |
| EDL-Export implementieren | **Gering** (0.5 Tage) | `otio.adapters.write_to_file()` |
| FCP XML Export + Resolve-Test | **Mittel** (1-2 Tage) | Manuelle Validierung noetig |
| Timeline-UI an OTIO-Modell anbinden | **Hoch** (3-5 Tage) | QGraphicsView muss OTIO lesen |

**Risiko:** Gering. OTIO ist Industrie-Standard (ASWF/Pixar), stabil, gut dokumentiert.

---

## 4. Video-Analyse & Suche: Vector-DB Vergleich

### 4.1 Altes Problem

- **SQLiteVectorStore** im Python-Prototyp: Eigenbau-Vektorsuche in SQLite — langsam, kein ANN-Index
- **5-Schritt-Pipeline** ist schwer und sequentiell: Proxy → SceneDetect → RAFT Motion → Moondream Caption → SigLIP Embedding
- Pipeline braucht ~15-30 Min pro Video (GPU-bound)
- Kein semantischer Text-zu-Video Search ("finde Clips mit Lasern")

### 4.2 Neue Loesungsvorschlaege

#### LanceDB vs ChromaDB

| Kriterium | LanceDB | ChromaDB | Empfehlung |
|-----------|---------|----------|------------|
| Architektur | Embedded (Rust-Core, memory-mapped) | Embedded (Python + hnswlib) | **LanceDB** |
| Server noetig? | Nein | Nein | Gleich |
| Startup-Zeit | Near-instant (mmap) | Langsam (HNSW-Index in RAM laden) | **LanceDB** |
| RAM bei 100k Vektoren | Minimal (mmap, lazy load) | Hoch (ganzer Index im RAM) | **LanceDB** |
| Disk-Footprint | Klein (Lance columnar, komprimiert) | Groesser (Parquet + SQLite) | **LanceDB** |
| CLIP/SigLIP Integration | Built-in (`lancedb.embeddings.OpenCLIP`) | Manuell | **LanceDB** |
| Metadata neben Vektoren | Ja (gleiche Tabelle) | Ja (internes SQLite) | Gleich |
| Such-Latenz (100k, 1152-dim) | ~100ms brute-force (kein Index noetig) | ~50ms (HNSW, aber RAM-hungrig) | Gleich |
| Python 3.11+ / Windows | Ja | Ja | Gleich |
| Dependencies | Leichtgewichtig (Rust binary) | Schwer (Clickhouse-Komponenten) | **LanceDB** |

#### Pipeline-Optimierung: Die schwere 5-Schritt-Pipeline ersetzen

**Vorschlag: 3-Schritt-Pipeline (statt 5):**

| Schritt | Alt (Prototyp) | Neu (v2) | Vorteil |
|---------|---------------|----------|---------|
| 1 | Proxy → SceneDetect → Motion (3 Schritte) | **SceneDetect + Motion in einem Pass** | SceneDetect liefert Keyframes, Motion berechnet nur zwischen Szenen-Grenzen |
| 2 | Moondream Caption (separater Schritt) | **Optional / On-Demand** | Captions nur generieren wenn User sucht — nicht im Voraus |
| 3 | SigLIP Embedding | **SigLIP Embedding (unveraendert)** | Keyframes der Szenen → 1152-dim Vektoren → LanceDB |

**Neue Text-zu-Video Suche (ohne Captions):**
- SigLIP unterstuetzt nativ Text-zu-Bild Similarity
- User tippt "Laser Show" → SigLIP text-encoder → Cosine-Similarity gegen alle Clip-Embeddings in LanceDB
- Kein Moondream noetig fuer Suche! (nur fuer UI-Anzeige von Beschreibungen)

### 4.3 Python Library Empfehlung

| Library | Version | Zweck |
|---------|---------|-------|
| `lancedb` | >=0.15 | Vektor-DB fuer Clip-Embeddings + Metadata |
| `scenedetect[opencv]` | >=0.6.7 | Scene Detection (ContentDetector) |
| `transformers` + SigLIP | >=5.0 | Embedding-Generierung (1152-dim) |

**SQLite behalten fuer:** Projekte, Einstellungen, Beatgrids, Timelines (relationale Daten)
**LanceDB nutzen fuer:** Clip-Embeddings, Szenen-Embeddings, semantische Suche

### 4.4 Implementierungs-Aufwand

| Task | Aufwand | Abhaengigkeit |
|------|---------|---------------|
| LanceDB integrieren (Tabellen: clips, scenes) | **Mittel** (2 Tage) | Ersetzt SQLiteVectorStore |
| SceneDetect + Motion-Analyse Kombination | **Mittel** (2-3 Tage) | SceneDetect Keyframes als Motion-Input |
| SigLIP Text-zu-Video Suche | **Gering** (1 Tag) | SigLIP text-encoder + LanceDB query |
| Moondream als On-Demand Feature | **Gering** (1 Tag) | Lazy-Load statt Pipeline-Schritt |
| Migration alter Embeddings → LanceDB | **Gering** (0.5 Tage) | Einmal-Migration |

**Risiko:** Gering. LanceDB ist production-ready, SigLIP text-search ist gut dokumentiert.

---

## 5. Audio DJ-Engine: Beat/Downbeat-Tracking

### 5.1 Altes Problem

- **madmom** war State-of-the-Art fuer Beat/Downbeat-Detection
- **madmom ist KAPUTT auf Python 3.11+** (nutzt `collections.MutableSequence`, entfernt in Python 3.10)
- **essentia hat KEINE Windows-Python-Bindings** (nur Linux/macOS)
- **librosa** funktioniert, aber Beat-Detection ist die schwaechste der drei
- **BeatNet** im Prototyp: Funktioniert, aber Projekt ist nicht aktiv maintained
- Kein zuverlaessiges Downbeat-Tracking → Phrase-Erkennung ungenau

### 5.2 Neue Loesungsvorschlaege

#### Bibliotheks-Vergleich (Windows + Python 3.11+)

| Feature | librosa 0.11 | beat_this (CPJKU) | madmom | essentia |
|---------|-------------|-------------------|--------|----------|
| **Windows-kompatibel** | Ja | Ja | NEIN (Python <3.10) | NEIN (kein Windows) |
| **Python 3.11+** | Ja | Ja | NEIN | NEIN |
| **Beat-Detection** | Gut (Onset+DP) | **Exzellent** (PyTorch RNN) | Exzellent (DBN) | Gut |
| **Downbeat-Detection** | Nein (manuell) | **Ja** (nativ) | Exzellent (DBNDownBeat) | Ja |
| **GPU-Beschleunigung** | Nein | **Ja** (PyTorch CUDA) | Nein | Nein |
| **Lange Dateien (120 Min)** | RAM-intensiv (~320MB) | Chunked moeglich | Stream-basiert | Stream-basiert |
| **Key-Detection** | Chroma + K-S Algo | Nein | Nein | Ja (KeyExtractor) |
| **Struktur-Segmentierung** | Ja (Laplacian) | Nein | Nein | Begrenzt |

#### Empfohlener Stack

```
Audio-Analyse Pipeline v2:
    │
    ├─ BPM + Beats + Downbeats ──→ beat_this (PyTorch, GPU)
    │    Fallback: librosa.beat.beat_track()
    │
    ├─ Key Detection ──→ librosa (Chroma + Krumhansl-Schmuckler)
    │    Alternative: essentia CLI via subprocess (wenn installiert)
    │
    ├─ Energie / Loudness ──→ librosa (RMS + Spectral)
    │
    ├─ Struktur-Segmentierung ──→ librosa (Laplacian Segmentation)
    │    (Intro/Verse/Chorus/Drop/Outro)
    │
    ├─ Spektral-Analyse (8-Band) ──→ librosa (FFT) — wie im Prototyp
    │
    └─ Stem-Separation ──→ demucs (unveraendert, GPU)
```

**beat_this** ist der offizielle Nachfolger von madmom:
- Gleiche Forschungsgruppe (CPJKU Linz)
- PyTorch-basiert (GPU-beschleunigt)
- Python 3.11+ kompatibel
- Nativer Downbeat-Detection
- Optionaler Non-madmom Postprocessing-Modus (kein madmom als Dependency noetig)

### 5.3 Python Library Empfehlung

| Library | Version | Zweck |
|---------|---------|-------|
| `librosa` | >=0.11.0 | Spektral, Energie, Struktur, Key, Onsets |
| `beat-this` | >=latest | Beat + Downbeat Detection (GPU) |
| `demucs` | >=4.0.1 | Stem Separation (unveraendert) |
| `scipy` | >=1.17 | DSP-Operationen (Filter, Ducking) |

**ENTFERNEN:** madmom, BeatNet (veraltet, inkompatibel)

### 5.4 Implementierungs-Aufwand

| Task | Aufwand | Abhaengigkeit |
|------|---------|---------------|
| beat_this integrieren (Beat + Downbeat) | **Mittel** (2 Tage) | PyTorch CUDA Setup vorhanden |
| librosa-Pipeline (Spektral, Energie, Key, Struktur) | **Gering** (1-2 Tage) | Groesstenteils aus Prototyp uebernehmen |
| Phrase-Detection aus Downbeats ableiten | **Mittel** (2 Tage) | Downbeats → 4er/8er Gruppen → Phrasen |
| DJ-Mix Chunking (120 Min Files) | **Mittel** (1-2 Tage) | Sliding-Window Analyse |
| ModelManager-Integration (VRAM-Sharing) | **Gering** (1 Tag) | beat_this + demucs nacheinander |

**Risiko:** Mittel. beat_this ist relativ neu — ausfuehrlich testen mit elektronischer Musik.

---

## 6. Konvertierung/Proxies: FFmpeg NVENC

### 6.1 Altes Problem

- Prototyp nutzt bereits `h264_nvenc`, aber:
  - Kein systematischer Proxy-Workflow
  - Keine Quality-Presets fuer verschiedene Anwendungsfaelle
  - Convert-Tab im Rebuild ist basic (nur Resolution/FPS/Codec)
  - Keine Hardware-Decode (nur Encode)
  - Kein Batch-Fortschritt mit ETA

### 6.2 Neue Loesungsvorschlaege

#### GTX 1060 NVENC Capabilities

| Codec | Encode | Decode | Qualitaet |
|-------|--------|--------|-----------|
| H.264 | Ja (6th gen NVENC) | Ja (NVDEC) | ~x264 "fast" Preset |
| H.265/HEVC | Ja | Ja | Unter x265 Software |
| VP9 | Nein | Nur 8-bit | — |
| AV1 | Nein (RTX 40+) | Nein | — |

**Limitation GTX 1060:**
- Keine B-Frames in H.264 NVENC → ~15% groessere Dateien
- Max 5 gleichzeitige NVENC Sessions (seit 2025 Treiber-Update)
- 6GB VRAM wird zwischen Encoding und AI-Modellen geteilt

#### Empfohlene Preset-Profile

**1. Edit-Proxy (schnell, klein, zum Editieren):**
```bash
ffmpeg -hwaccel cuda -hwaccel_output_format cuda \
    -i input.mp4 \
    -vf "scale_cuda=960:540" \
    -c:v h264_nvenc -preset p1 -cq 28 \
    -c:a aac -b:a 128k \
    proxy.mp4
```
- Geschwindigkeit: ~5-10x Realtime (1080p → 540p)
- Dategroesse: ~50MB pro Stunde

**2. Master-Export (Qualitaet, finale Ausgabe):**
```bash
ffmpeg -hwaccel cuda \
    -i input.mp4 \
    -c:v h264_nvenc -preset p4 -cq 18 -b:v 15M \
    -c:a aac -b:a 320k \
    master.mp4
```
- Geschwindigkeit: ~3-5x Realtime
- Qualitaet: Nah an x264 medium

**3. DaVinci-Proxy (NLE-kompatibel, CPU):**
```bash
ffmpeg -i input.mp4 \
    -vf "scale=1280:720,format=yuv422p" \
    -c:v dnxhd -profile:v dnxhr_lb \
    -c:a pcm_s16le \
    proxy.mxf
```
- Beste Kompatibilitaet mit DaVinci Resolve
- CPU-encoded (langsamer, aber universell)

#### Hardware-Decode + Encode Pipeline

```
Input → NVDEC (GPU Decode) → GPU Memory → Scale (CUDA) → NVENC (GPU Encode) → Output
```
- Gesamte Pipeline auf GPU — CPU ist frei fuer andere Tasks
- Key: `-hwaccel cuda -hwaccel_output_format cuda` haelt Frames im GPU-Speicher

### 6.3 Python Library Empfehlung

| Library | Zweck | Empfehlung |
|---------|-------|------------|
| `subprocess` (stdlib) | FFmpeg-Aufrufe | **Ja** — volle Kontrolle, kein Dependency-Risiko |
| `ffmpeg-python` | Chainable API | **Nein** — seit 2019 unmaintained |
| `python-ffmpeg` | Neuere Alternative | **Evaluieren** — aktiv maintained, saubere API |

**Empfehlung:** `subprocess.Popen` mit Fortschritts-Parsing (stderr-Zeilen `frame=` / `time=` parsen)

### 6.4 Implementierungs-Aufwand

| Task | Aufwand | Abhaengigkeit |
|------|---------|---------------|
| NVENC-Detection (Capability Check) | **Gering** (0.5 Tage) | `ffmpeg -encoders` parsen |
| 3 Preset-Profile implementieren | **Gering** (1 Tag) | Proxy, Master, DaVinci |
| Fortschritts-Parsing (ETA) | **Mittel** (1-2 Tage) | FFmpeg stderr → Progress-Signal |
| Batch-Konvertierung mit Queue | **Mittel** (1-2 Tage) | QThread Worker + Task-Manager |
| Hardware-Decode Pipeline | **Gering** (1 Tag) | `-hwaccel cuda` Flag |
| VRAM-Koordination (NVENC vs AI-Modelle) | **Mittel** (1 Tag) | ModelManager-Integration |

**Risiko:** Gering. FFmpeg NVENC ist ausgereift, GTX 1060 ist gut unterstuetzt.

---

## 7. Gesamtarchitektur-Empfehlung

### 7.1 Schichten-Architektur

```
┌─────────────────────────────────────────────────────────┐
│                    PySide6 GUI Layer                     │
│  ┌──────────┬──────────┬──────────┬──────────┐          │
│  │  MEDIA   │   EDIT   │ CONVERT  │ DELIVER  │          │
│  │  Tab     │   Tab    │  Tab     │  Tab     │          │
│  └──────────┴──────────┴──────────┴──────────┘          │
│  ┌──────────────────────────────────────────────┐       │
│  │  Timeline Widget (QGraphicsView ← OTIO)      │       │
│  │  Waveform Widget | Anchor Editor | Chat Dock │       │
│  └──────────────────────────────────────────────┘       │
├─────────────────────────────────────────────────────────┤
│                   Service Layer                          │
│  ┌────────────┬────────────┬────────────┬────────────┐  │
│  │ AudioSvc   │ VideoSvc   │ PacingSvc  │ ExportSvc  │  │
│  │ (librosa,  │ (SceneDet, │ (Director, │ (FFmpeg,   │  │
│  │  beat_this,│  SigLIP,   │  Anchors,  │  NVENC)    │  │
│  │  demucs)   │  Motion)   │  Clips)    │            │  │
│  └────────────┴────────────┴────────────┴────────────┘  │
├─────────────────────────────────────────────────────────┤
│                   Data Layer                             │
│  ┌──────────────────┬───────────────────────┐           │
│  │ SQLite/SQLAlchemy │ LanceDB               │           │
│  │ (Projekte,        │ (Clip-Embeddings,      │           │
│  │  Beatgrids,       │  Szenen-Embeddings,    │           │
│  │  Einstellungen)   │  Semantische Suche)    │           │
│  └──────────────────┴───────────────────────┘           │
│  ┌──────────────────────────────────────────────┐       │
│  │ OpenTimelineIO (Timeline-Modell + Export)     │       │
│  └──────────────────────────────────────────────┘       │
├─────────────────────────────────────────────────────────┤
│                   Infrastructure                         │
│  ┌──────────────┬──────────────┬──────────────────┐     │
│  │ ModelManager  │ GPUManager   │ TaskManager       │     │
│  │ (VRAM Mutex)  │ (CUDA Check) │ (Worker Threads)  │     │
│  └──────────────┴──────────────┴──────────────────┘     │
│  ┌──────────────────────────────────────────────┐       │
│  │ FFmpeg (subprocess) + NVENC                   │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Datenfluss: Von Import bis Export

```
1. IMPORT (Media Tab)
   User importiert Videos + Audio
       ↓
   IngestService validiert, erstellt DB-Eintraege
       ↓
   [Background] ProxyWorker erstellt Edit-Proxies (NVENC 540p)

2. ANALYSE (automatisch nach Import)
   Audio:
     ├─ beat_this → BPM, Beats, Downbeats → SQLite (beatgrids)
     ├─ librosa → Energie, Spektral, Struktur, Key → SQLite (audio_tracks)
     └─ demucs → Stems (vocals/drums/bass/other) → Dateisystem

   Video:
     ├─ SceneDetect → Szenen-Grenzen → SQLite (scenes)
     ├─ RAFT Motion → Motion-Score pro Szene → SQLite (scenes)
     └─ SigLIP → 1152-dim Embedding pro Szene → LanceDB

3. EDITING (Edit Tab)
   User setzt Anchors auf Timeline (OTIO Marker mit Metadata)
       ↓
   PacingService generiert Cut-Liste:
     - Beats/Downbeats aus beat_this
     - Trigger-Staerken (kicks, snares, energy)
     - Clip-Selektion via LanceDB (semantisch) oder Motion-Matching
     - Anchor-Praeferenzen anwenden (Cosine-Similarity)
       ↓
   Timeline als OTIO-Objekt im Speicher

4. EXPORT (Deliver Tab)
   OTIO Timeline → FFmpeg Concat-Filter → NVENC Master Export
       ↓
   Optional: OTIO → EDL/FCP XML → DaVinci Resolve
```

### 7.3 Entscheidungsmatrix: Was uebernehmen, was ersetzen

| Komponente | Prototyp | Rebuild v2 | Aktion |
|------------|----------|-----------|--------|
| Timeline-Modell | `List[TimelineClip]` | OTIO `Timeline` | **Ersetzen** |
| Anchor-System | Eigene `AnchorData` | OTIO `Marker` + Metadata | **Ersetzen** |
| Vektor-Suche | SQLiteVectorStore | LanceDB | **Ersetzen** |
| Beat-Detection | BeatNet/madmom | beat_this | **Ersetzen** |
| Spektral-Analyse | librosa 8-Band | librosa 8-Band | **Uebernehmen** |
| Struktur-Analyse | Eigenbau Novelty | librosa Laplacian | **Verbessern** |
| Stem-Separation | Demucs | Demucs | **Uebernehmen** |
| Scene Detection | PySceneDetect | PySceneDetect | **Uebernehmen** |
| Motion Analysis | RAFT (PyTorch) | RAFT (PyTorch) | **Uebernehmen** |
| Embeddings | SigLIP 1152-dim | SigLIP 1152-dim | **Uebernehmen** |
| Captioning | Moondream2 | Moondream2 (on-demand) | **Optimieren** |
| GPU-Management | Eigenbau Mutex | ModelManager Singleton | **Uebernehmen** |
| Proxy-Erstellung | Basic FFmpeg | NVENC Preset-Profile | **Verbessern** |
| Rendering | FFmpeg h264_nvenc | FFmpeg h264_nvenc | **Uebernehmen** |
| Pacing-Konstanten | constants.py | Uebernehmen + UI-Slider | **Uebernehmen** |
| Clip-Selektion | 4 Strategien | Uebernehmen + LanceDB Query | **Verbessern** |
| KI-Swarm | 3 Agenten | Beibehalten | **Uebernehmen** |
| DB-Schema | SQLAlchemy + SQLite | SQLAlchemy + SQLite + LanceDB | **Erweitern** |

---

## 8. Implementierungs-Roadmap

### Phase 1: Foundation (Woche 1-2)

| # | Task | Aufwand | Prioritaet |
|---|------|---------|-----------|
| 1.1 | OTIO installieren, Timeline-Modell erstellen | 2 Tage | HOCH |
| 1.2 | LanceDB installieren, Embedding-Tabelle erstellen | 1 Tag | HOCH |
| 1.3 | beat_this installieren, Beat/Downbeat testen | 2 Tage | HOCH |
| 1.4 | NVENC Detection + 3 Preset-Profile | 1.5 Tage | MITTEL |
| 1.5 | Kritische Bugs aus Audit fixen (CRIT-01 bis CRIT-04) | 2 Tage | HOCH |

### Phase 2: Pipeline (Woche 3-4)

| # | Task | Aufwand | Prioritaet |
|---|------|---------|-----------|
| 2.1 | 3-Schritt Video-Pipeline (SceneDet+Motion → SigLIP → LanceDB) | 3 Tage | HOCH |
| 2.2 | Audio-Pipeline (beat_this + librosa Spektral/Energie/Struktur) | 3 Tage | HOCH |
| 2.3 | SigLIP Text-zu-Video Suche via LanceDB | 1 Tag | MITTEL |
| 2.4 | Proxy-Erstellung mit NVENC im Ingest-Flow | 1.5 Tage | MITTEL |

### Phase 3: Intelligence (Woche 5-6)

| # | Task | Aufwand | Prioritaet |
|---|------|---------|-----------|
| 3.1 | Pacing-Engine mit Downbeats + Phrasen (aus beat_this) | 3 Tage | HOCH |
| 3.2 | Anchor-System auf OTIO-Marker migrieren | 2 Tage | HOCH |
| 3.3 | Clip-Selektion mit LanceDB Semantic Search | 2 Tage | HOCH |
| 3.4 | Smart Director (Prototyp-Logik portieren) | 3 Tage | MITTEL |

### Phase 4: Export & Polish (Woche 7-8)

| # | Task | Aufwand | Prioritaet |
|---|------|---------|-----------|
| 4.1 | OTIO → EDL/FCP XML Export | 1.5 Tage | HOCH |
| 4.2 | Master-Export mit NVENC + Crossfades | 2 Tage | HOCH |
| 4.3 | Fortschritts-Parsing + ETA im Task-Manager | 1.5 Tage | MITTEL |
| 4.4 | Timeline-UI an OTIO-Modell anbinden | 4 Tage | HOCH |

### Gesamt-Aufwand

| Phase | Tage | Kalenderwochen |
|-------|------|---------------|
| Foundation | ~8.5 | 2 |
| Pipeline | ~8.5 | 2 |
| Intelligence | ~10 | 2 |
| Export & Polish | ~9 | 2 |
| **Total** | **~36 Tage** | **~8 Wochen** |

---

## Quellen

- [OpenTimelineIO (ASWF)](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) — v0.18.1
- [LanceDB](https://github.com/lancedb/lancedb) — Embedded Vector DB
- [beat_this (CPJKU)](https://github.com/CPJKU/beat_this) — PyTorch Beat/Downbeat Detection
- [NVIDIA NVENC FFmpeg Guide](https://developer.nvidia.com/blog/nvidia-ffmpeg-transcoding-guide/)
- [madmom Python 3.10+ Issue](https://github.com/CPJKU/madmom/issues/478)
- [essentia Windows Issue](https://github.com/MTG/essentia/issues/1130)
- [LanceDB vs ChromaDB (Zilliz)](https://zilliz.com/comparison/chroma-vs-lancedb)
- PB Studio Python-Prototyp (intern): `2_pb_studio_Version_B_Nvidia-1/`
- PB Studio C#-Prototyp (intern): `Pb_Studio_Windows_version_C#/PB_Studio_Native/`
