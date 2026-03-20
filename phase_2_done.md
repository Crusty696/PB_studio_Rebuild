# Phase 2: Pipeline (Ingest & Analyse) — ABGESCHLOSSEN

**Datum:** 2026-03-20
**Status:** DONE

---

## SEKTOR 1: 3-Schritt Video-Pipeline (Task 2.1)

**Datei:** `services/video_analysis_service.py`

### Implementiert:
1. **SceneDetect + RAFT Motion** in einem Durchgang
   - PySceneDetect `ContentDetector` für Szenen-Erkennung
   - OpenCV Frame-Differenz für Motion-Score (0.0–1.0) innerhalb jeder Szene
   - Fallback auf Single-Scene wenn PySceneDetect nicht installiert

2. **Keyframe-Extraktion**
   - FFmpeg extrahiert 1 Keyframe pro Szene (Mitte)
   - 384x384 Resize mit Padding (SigLIP-optimiert)
   - Gespeichert in `storage/keyframes/`

3. **SigLIP 1152-dim Embeddings → LanceDB**
   - ModelManager Singleton lädt SigLIP (`google/siglip-base-patch16-384`)
   - Batch-Verarbeitung (8 Bilder pro Batch, VRAM-schonend für GTX 1060)
   - L2-normalisierte Embeddings in LanceDB `clip_embeddings` Tabelle
   - Szenen zusätzlich in SQLite `scenes` Tabelle gespeichert

### Neue Dateien:
- `services/video_analysis_service.py` — Vollständige Pipeline
- `services/model_manager.py` — `load_siglip()` Methode hinzugefügt

### Worker:
- `VideoAnalysisPipelineWorker` — QThread mit Progress + Cancel Support

---

## SEKTOR 2: Proxy-Erstellung (Task 2.4)

### Implementiert:
- `ProxyCreationWorker` nutzt `ConvertService.convert()` mit `edit_proxy` Preset
- **Auto-Trigger:** Jedes importierte Video bekommt automatisch einen NVENC 540p Proxy
- Proxy-Pfad wird in SQLite `video_clips.proxy_path` gespeichert
- Progress-Callback für Fortschrittsanzeige im Task Manager

### Flow:
```
Video importieren → ingest_video() → SQLite → ProxyCreationWorker → NVENC 540p → proxy_path in DB
```

---

## SEKTOR 3: SigLIP Text-zu-Video Suche (Task 2.3)

### Implementiert:
- **Suchleiste** im MEDIA Workspace (oben über den Pools)
  - SigLIP Badge + Input + Suchen-Button + Clear-Button
  - Enter-Taste löst Suche aus
- **Backend:** `text_to_embedding()` konvertiert Text → 1152-dim SigLIP Vektor
- **LanceDB `.search()`** findet relevanteste Szenen nach Distanz
- **UI-Update:** Video Pool zeigt Suchergebnisse (Name, Szene, Motion, Distanz)
- **Clear-Button** setzt zurück auf normale Ansicht

### Worker:
- `SemanticSearchWorker` — Non-blocking Suche im Hintergrund

---

## SEKTOR 4: Media UI & Abbrechen-Button

### Bereits vorhanden (Phase 1):
- **Video Pool** und **Audio Pool** als getrennte Listen (QTableWidget)
- **Ordner importieren** Button (rekursiv, alle Audio/Video Extensions)
- **Sammlung bereinigen** Button mit Bestätigungs-Dialog
- **Abbrechen-Button** im TaskManagerWidget für laufende Prozesse

### Neu in Phase 2:
- **SigLIP Suchleiste** über den Pools
- **Video-Pipeline Button** in Analyse-Gruppe
- Auto-Proxy bei Video-Import

---

## Architektur-Übersicht

```
Video Import → ingest_video() → SQLite
                    ↓
            ProxyCreationWorker (NVENC 540p)
                    ↓
            proxy_path → SQLite

User klickt "Video-Pipeline":
    ↓
VideoAnalysisPipelineWorker
    ├── 1. SceneDetect (ContentDetector)
    ├── 1b. Motion Scores (OpenCV Frame-Diff)
    ├── 2. Keyframe Extraction (FFmpeg 384x384)
    ├── 3. SigLIP Embeddings (ModelManager)
    ├── 3b. Store in LanceDB
    └── 3c. Store Scenes in SQLite

User sucht Text:
    ↓
SemanticSearchWorker
    ├── text_to_embedding() (SigLIP Text Encoder)
    ├── LanceDB .search() (Cosine Similarity)
    └── UI Update (Video Pool → Suchergebnisse)
```

---

## Abhängigkeiten (Phase 1 Foundation)

| Komponente | Status |
|-----------|--------|
| ModelManager Singleton | ✅ + `load_siglip()` |
| VectorDBService (LanceDB) | ✅ 1152-dim Schema |
| ConvertService (NVENC) | ✅ edit_proxy Preset |
| IngestService | ✅ + Auto-Proxy Trigger |
| GlobalTaskManager | ✅ Cancel Support |
| CancellableMixin | ✅ should_stop() Pattern |

---

## Nächste Phase

Phase 3: Smart Director System
- Few-shot Clip Selection
- Audio-Feature Matching
- Semantic Video-to-Music Matching
- Advanced Pacing Engine Integration
