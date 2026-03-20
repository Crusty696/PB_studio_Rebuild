# Phase 1 Foundation — Abgeschlossen

**Datum:** 2026-03-20
**Status:** DONE

---

## Sektor 1: Dependencies (PoC-Validated)

**pyproject.toml aktualisiert mit:**
- `opentimelineio >= 0.18.0` — Timeline-Backend (v0.18.1 installiert)
- `lancedb >= 0.20.0` — Embedded Vector-DB (v0.30.0 installiert)
- `beat-this` — Beat/Downbeat-Erkennung via GPU (v0.1, GitHub-Source)
- `pyarrow >= 18.0.0` — Arrow-Backend fuer LanceDB (v23.0.1 installiert)

**Alle Imports verifiziert. App startet fehlerfrei.**

---

## Sektor 2: OTIO Timeline Backend

**Datei:** `services/timeline_service.py`

- Interne Timeline-Logik durch `otio.schema.Timeline` ersetzt
- `TimelineService` Klasse mit:
  - `create_timeline()`, `add_clip()`, `add_transition()`, `add_marker()`
  - Multi-Track Support (Video + Audio)
  - Marker als OTIO-Marker mit `pb_studio` Metadata-Namespace
  - Beatgrid als Timeline-Metadata
  - Export: `.otio` (JSON) und `.edl` (CMX 3600 / DaVinci Resolve)
  - Save/Load Roundtrip verifiziert
- **PoC-Erkenntnis R2 implementiert:** `safe_get_metadata()` konvertiert OTIO `AnyVector` -> Python `list` und `AnyDictionary` -> `dict` vor jedem Zugriff auf `audio_features`
- **Test bestanden:** Marker-Metadata (audio_features, similarity_threshold) ueberleben Save/Load Roundtrip korrekt

---

## Sektor 3: LanceDB Setup

**Datei:** `services/vector_db_service.py`

- `VectorDBService` mit LanceDB (lokal in `data/vector/`)
- Tabelle `clip_embeddings` mit 1152-dim SigLIP-Vektoren
- Schema: id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding
- Methoden: `add_embedding()`, `add_embeddings_batch()`, `search()`, `search_by_text()`, `count()`, `delete_by_video()`
- Filtered Search (z.B. `motion_score > 0.5`) funktioniert
- **Test bestanden:** 10 Eintraege inserted, Top-3 Nearest-Neighbor-Suche in < 100ms

---

## Sektor 4: Audio-Analyse mit beat_this + Chunking

**Datei:** `services/beat_analysis_service.py`

- `BeatAnalysisService` mit GPU-beschleunigter Beat/Downbeat-Erkennung
- `dbn=False` gesetzt (verhindert madmom-Abhaengigkeit)
- **Chunked Processing implementiert (PoC-Erkenntnis R4):**
  - GTX 1060 = 6GB VRAM, 60-Min-Mix = ~2.9GB VRAM
  - Audio wird in 10-Minuten-Segmente (CHUNK_DURATION_SEC = 600s) aufgeteilt
  - 5 Sekunden Overlap zwischen Chunks fuer saubere Beat-Uebergaenge
  - Chunks als temporaere WAV-Dateien (beat_this erwartet Dateipfad)
  - Beat-Timestamps werden mit globalem Offset zusammengesetzt
  - Overlap-Deduplizierung: nur Beats > 0.05s nach dem letzten akzeptierten Beat
- Lazy Model Loading + explizites `unload()` fuer VRAM-Freigabe
- `analyze_and_store()` schreibt Ergebnisse in SQLite Beatgrid
- BPM aus Median der Beat-Intervalle berechnet

---

## Sektor 5: NVENC Preset-Profile

**Datei:** `services/convert_service.py`

- 3 PoC-validierte Preset-Profile:

| Preset | Aufloesung | Codec | Preset | CQ | Einsatz |
|--------|-----------|-------|--------|----|---------|
| `edit_proxy` | 540p | h264_nvenc | p1 | 28 | Schnelles Editing (~50MB/h) |
| `master` | 1080p | h264_nvenc | p4 | 18 | Finale Qualitaet (15Mbps) |
| `davinci` | 720p | DNxHR LB | — | — | DaVinci Resolve Import |

- `detect_nvenc()` prueft Verfuegbarkeit von h264_nvenc, hevc_nvenc, CUDA hwaccel
- `convert()` mit FFmpeg `-progress pipe:1` fuer sauberes Fortschritts-Parsing
- Progress-Callback: `out_time_ms` und `out_time` werden geparsed
- Hardware-Decode (`-hwaccel cuda`) bei NVENC-Presets aktiv
- **KEIN AV1** — Pascal-Karten (GTX 1060) haben keinen echten AV1-Encoder
- NVENC erkannt: h264_nvenc=True, hevc_nvenc=True, cuda=True

---

## Verifikation

```
[OK] OTIO Timeline: clips=2, markers=1, AnyVector->list works
[OK] LanceDB: count=10, search top-3 works, dim=1152
[OK] BeatAnalysisService: device=cuda, chunk_size=600s
[OK] ConvertService: 3 presets, h264_nvenc=True, cuda=True
     edit_proxy: Edit-Proxy (540p) (available=True)
     master: Master (1080p) (available=True)
     davinci: DaVinci-Proxy (720p) (available=True)

PHASE 1 FOUNDATION: ALL SERVICES VERIFIED
```

---

## Neue Dateien

| Datei | Sektor | Zweck |
|-------|--------|-------|
| `services/timeline_service.py` | 2 | OTIO Timeline Backend |
| `services/vector_db_service.py` | 3 | LanceDB Vector-DB Service |
| `services/beat_analysis_service.py` | 4 | beat_this + Chunked Processing |
| `services/convert_service.py` | 5 | NVENC Preset-Profile + Progress |
| `data/vector/` | 3 | LanceDB Datenverzeichnis |
| `exports/phase1_test.otio` | 2 | Test-Export (kann geloescht werden) |

## Naechste Schritte (Phase 2: Pipeline)

1. 3-Schritt Video-Pipeline (SceneDet + Motion -> SigLIP -> LanceDB)
2. Audio-Pipeline (beat_this + librosa Spektral/Energie/Struktur)
3. SigLIP Text-zu-Video Suche via LanceDB
4. Proxy-Erstellung mit NVENC im Ingest-Flow
