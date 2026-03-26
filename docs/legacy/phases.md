# Phase History

> Zusammenfassung der drei Entwicklungsphasen. Rekonstruiert aus den geloeschten
> Phase-Dokumenten (`phase_1_done.md`, `phase_2_done.md`, `phase_3_done.md`).
> Original geloescht in Commit `7d95560` (2026-03-24).

---

## Phase 0: Foundation Rebuild (2026-03-19)

**Quelle:** `master_rebuild_bericht.md` (geloescht)

### Was gebaut wurde:
1. **Core & Media Ingest**
   - Librosa 0.11 BPM-Bug gefixt (`ndarray.flat[0]`)
   - Beat-Grid Speicherung in SQLite
   - FFprobe Duration Extraction
   - Getestet mit echten Files: MP3, WAV, M4A + 5 Sora Videos

2. **Director's Desk**
   - `InteractiveTimeline` (QGraphicsView) ersetzt altes Paint-Widget
   - 2 Tracks: Audio + Video
   - Drag & Drop mit DB-Sync
   - `TimelineEntry` DB-Modell

3. **Production / Export**
   - `ExportService` mit FFmpeg Concat Demuxer
   - Auto-Scaling + Padding fuer unterschiedliche Aufloesungen
   - Audio-Mixing
   - Progress Callback

4. **QA**
   - 13-Test Suite mit echten Daten
   - Windows-Fixes: SQLite Isolation Level, FFmpeg Timeouts
   - Full E2E Pipeline: Ingest -> Analyze -> Timeline -> Export (113s)

### Design Overhaul (v0.2.0)
**Quelle:** `design_bericht.md` (geloescht)

- **Dark Steel Theme:** `styles/dark_steel.qss`
  - Palette: Anthrazit #15171c, Cyan #00d4ff, Violet #7c3aed
- **Video Preview:** FFmpeg Frame-Extraction (320x180), Timer-Playback
- **Windows-Fix:** `CREATE_NO_WINDOW` Flag fuer subprocess

---

## Phase 1: Foundation Stack (2026-03-20)

**Quelle:** `phase_1_done.md` (geloescht)

### Sektoren:
1. **Dependencies** — pyproject.toml erweitert: opentimelineio, lancedb, beat-this, pyarrow
2. **OTIO Timeline Backend** — `TimelineService` mit Multi-Track, Markers, `safe_get_metadata()`
3. **LanceDB Setup** — `VectorDBService` mit 1152-dim SigLIP Schema, Filtered Search
4. **Audio Analysis** — `BeatAnalysisService` mit Chunked Processing (10-min Segmente, 5s Overlap) fuer 6GB VRAM
5. **NVENC Presets** — 3 Profile (edit_proxy 540p, master 1080p, davinci 720p), CUDA HW-Pipeline

### Entscheidungen:
- Beat-This mit `dbn=False` (kein Madmom) → D-01
- LanceDB embedded statt ChromaDB → D-02
- NVENC Hardware-Encoding → D-03
- OTIO als Timeline-Format → D-04

---

## Phase 2: Semantic Pipeline (2026-03-20)

**Quelle:** `phase_2_done.md` (geloescht)

### Sektoren:
1. **3-Step Video Pipeline**
   - SceneDetect (ContentDetector) → Szenen-Grenzen
   - Motion Scoring (RAFT Optical Flow) → Bewegungsintensitaet
   - SigLIP Embeddings (1152-dim) → Semantische Vektoren in LanceDB
   - Keyframe-Extraction via FFmpeg

2. **Proxy Creation**
   - Auto-NVENC 540p Proxy bei Video-Import
   - Transparent fuer den User

3. **SigLIP Text-to-Video Search**
   - Semantische Suchleiste im MEDIA Workspace
   - `text_to_embedding()` + LanceDB Nearest-Neighbor
   - Ergebnis: Clips sortiert nach semantischer Aehnlichkeit

4. **Media UI**
   - Such-Bar mit Enter-Trigger
   - Pipeline-Button fuer Batch-Analyse
   - Auto-Proxy nach Import

### Entscheidung:
- SigLIP statt CLIP → D-08

---

## Phase 3: DJ Intelligence (2026-03-20)

**Quelle:** `phase_3_done.md` (geloescht)

### Sektoren:
1. **Advanced Pacing UI**
   - DJ-Style Controls im Inspector Panel
   - Base Cut Rate: 1/2/4/8/16 Beats
   - Energy Reactivity Slider (0-100%)
   - Breakdown Behavior: hold / slow_cuts / blackout

2. **Pacing Engine**
   - Audio-Duration bestimmt Timeline-Laenge
   - Per-Beat RMS Energy Berechnung
   - Effective Step = Base Rate * Energy Factor * Breakdown Modifier
   - LanceDB Semantic Search fuer Vibe-Keyword Matching
   - Intelligentes Video-Looping (Loop statt Schwarzbild)
   - Neue DB-Spalten: `downbeat_positions`, `energy_per_beat`

3. **Anchor System**
   - OTIO Markers mit `pb_studio` Metadata-Namespace
   - Anchor-Liste mit CRUD (Add/Remove/Sync)
   - Pacing Engine respektiert Anchors (fixe Clip-Positionen)
   - "Als KI-Regel lernen" Button → `AIPacingMemory` DB-Modell

### Ergebnis:
Die App kann jetzt automatisch beat-synchrone Schnitte generieren,
basierend auf Audio-Energie, manueller Pacing-Kurve und Anchor-Points.

---

## Feature Gap (Stand Phase 3)

**Quelle:** `feature_gap_analysis.md` (geloescht)

**Abdeckung:** 31 von 104 Features (29.8%) gegenueber Python-Prototyp + C#-Prototyp

### Groesste Luecken:
| Bereich | Fehlend | Beispiele |
|---------|---------|-----------|
| Media Ingest | 8 | Folder-Import, Drag&Drop, Thumbnail Grid, Rekordbox XML |
| Audio | 9 | Spectral Analysis, Mood/Genre, Key Detection, LUFS |
| Video Pipeline | 8 | UI-Integration der Pipeline-Ergebnisse |
| Timeline | 11 | Beat Grid Overlay, Waveform, Zoom, Trim, Undo/Redo |
| Anchor System | 7 | Komplett fehlend zum Zeitpunkt der Analyse |
| Director/Pacing | 12 | Flow Slider, Beat Weighting, Style Presets, ML Feedback |

**Hinweis:** Einige dieser Features wurden NACH der Gap-Analyse implementiert
(Anchor System, Folder-Import, LUFS). Die Zahlen sind historisch.

---

## Chronologie

| Datum | Milestone |
|-------|-----------|
| 2026-03-19 | Phase 0: Foundation Rebuild + Design Overhaul |
| 2026-03-20 | Phase 1: OTIO + LanceDB + Beat-This + NVENC |
| 2026-03-20 | Phase 2: Video Pipeline + SigLIP Search + Proxies |
| 2026-03-20 | Phase 3: DJ Pacing Engine + Anchor System |
| 2026-03-20 | Git-Cleanup: Media aus Tracking entfernt (bee8347) |
| 2026-03-23 | Dual-Agent E2E Testsystem Vorbereitung |
| 2026-03-24 | Grand Audit: 30+ Fixes (7d95560) |
| 2026-03-25 | KI-Gedaechtnis Schutz (375b1cd) |
