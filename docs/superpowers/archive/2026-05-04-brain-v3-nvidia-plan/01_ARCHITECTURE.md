# 01 — Architektur (Brain V3, NVIDIA)

## Übersicht

Brain V3 ist ein **Layer ÜBER** dem bestehenden Pacing-Code —
kein Ersatz. Der Eingriffspunkt ist die Pacing-Pipeline-Selektor-
Funktion (`services/pacing/pipeline.py` Klasse `PacingPipeline`,
Funktion-Name vor Code-Edit verifizieren), die an den
`BrainV3Reranker` delegiert wird (Phase 4).

V3 ist STRIKT getrennt von V1 und V2 — eigener Code-Namespace, eigene
DB-Pfade, eigener UI-Tab. Plan-Doc 02 #24.

**Architektur-Standard (User-Direktive 2026-05-05, F1):** PB Studio
Rebuild ist eine reine PySide6-Desktop-Anwendung. Es gibt **keinen
FastAPI-Server, kein REST-Layer, kein `localhost:8765`**. Alle
Aufrufe von der UI an Service-Module laufen **in-process**, das heißt
direkt als Python-Methoden-Aufrufe (ggf. ueber `QThread`-Worker fuer
Hintergrund-Operationen). Brain V3 stellt einen `BrainV3Service`-
Fassaden-Wrapper bereit, der die Service-Methoden unter einem
stabilen Interface buendelt — kein HTTP-Client, kein Router. Falls
spaeter ein REST-Wrapper fuer externe Clients gewollt ist, wird er
als optionale Zusatz-Phase 4.5 separat geplant; er ist **nicht** Teil
des aktuellen V3-Scopes.

```text
┌────────────── User-UI (PySide6 6.11) ──────────────────────┐
│ - Timeline-Cut-Item: 4-Klick-Popup (Hotkeys 1-4)           │
│ - Neuer Tab "Brain V3" (parallel zu studio_brain_window)   │
│ - Lern-Session-Dialog (15 unsicherste Cuts)                │
│ - Stats-Panel (Top-Buckets, Cold-Start-Status)             │
└─────────────────────┬──────────────────────────────────────┘
                      │ in-process Python-Aufruf (kein HTTP)
                      │ via BrainV3Service-Wrapper
┌─────────────────────▼──────────────────────────────────────┐
│ Service-Layer (in-process, direkt importiert von der UI)   │
│  Bestehend: services/project, audio, video, pacing, render │
│  NEU:        services/brain_v3 (BrainV3Service-Fassade)    │
└─────────────────────┬──────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────┐
│ Core (services/brain_v3/)                                  │
│                                                            │
│  brain_v3/                  brain_v3/audio/                │
│  ├ paths.py                 ├ subtrack_detector.py (P1) ✓  │
│  ├ hashing.py (P1) ✓        └ audio_embedder.py    (P2) ✓  │
│  ├ gpu_serializer.py(P2) ✓                                 │
│  ├ background_queue.py(P2) ✓                               │
│  ├ schemas/audio.py (P1) ✓  brain_v3/video/                │
│  └ schemas/video.py (P1) ✓  ├ visual_curves.py     (P1) ✓  │
│                             └ video_embedder.py    (P2) ✓  │
│                                                            │
│  brain_v3/storage/ (einzige Stelle mit sqlite_vec.load):   │
│  ├ sqlite_init.py     (P2) ✓                               │
│  ├ migration_runner.py(P2) ✓                               │
│  ├ embedding_cache.py (P2) ✓                               │
│  └ embedding_repository.py (P2) ✓                          │
│                                                            │
│  TODO Phase 3 (Brain-Core):                                │
│  ├ weight_store.py        ├ feedback_logger.py             │
│  ├ bridge_dimensions.py   ├ scorer.py                      │
│  ├ context_resolver.py    ├ smart_sampler.py               │
│  └ cold_start.py          └ brain_store.py                 │
│                                                            │
│  TODO Phase 4: reranker.py (Hook in clip_selector)         │
└─────────────────────┬──────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────┐
│ Persistenz                                                 │
│                                                            │
│  Pro Projekt:                  App-global:                 │
│  <Projekt>/brain_v3/           %APPDATA%\PB_Studio\        │
│    embeddings.db ✓               brain_v3\weights.db (P3)  │
│    state.db (P4)                 brain_v3\patterns.db (P3) │
│                                  brain_v3\embedding_cache.db ✓ │
│                                  brain_v3\embeddings\*.npy ✓│
│                                                            │
│  Alle SQLite mit WAL + identischem PRAGMA-Setup            │
└────────────────────────────────────────────────────────────┘
```

---

## Pacing-Pipeline (mit Brain V3, Phase 4)

```text
PacingService.generate_cut_list()
  │
  ▼
AdvancedPacingEngine produziert Cut-Positionen + trigger_type + strength
  │
  ▼
BrainV3Reranker.rerank(candidates, cut_context)   [delegiert von clip_selector]
  ├ FeatureExtractor      (Audio/Video-Features für Cut-Zeitpunkt)
  ├ BridgeDimensions      (17 Achsen-Werte berechnen)
  ├ ContextResolver       (6 Kontext-Slots aus Audio/Video ableiten)
  ├ WeightStore           (gelernte α/β über 5 Backoff-Levels lookup)
  └ Scorer                (gewichteter Score-Vektor → Final-Score pro Kandidat)
  │
  ▼
finale Cut-Liste mit metadata.brain_v3_scores (17 Sub-Scores pro Cut)
```

## Feedback-Pipeline (Phase 4)

```text
UI 4-Klick (Perfect / Fits / NotQuite / NoMatch)
  │
  ▼  in-process: BrainV3Service.feedback(cut_id, rating)
  │  (PySide6-Slot ruft Python-Methode direkt; kein HTTP)
FeedbackLogger.log(cut_id, rating)
  │
  ▼  Atomic Update auf 6 Backoff-Levels (0..5) × 17 Achsen = 102 Buckets
weights.db aktualisiert  (Beta-Bernoulli α/β-Inkremente)
state.db / feedback_events protokolliert Klick-Roh-Daten
```

---

## Daten-Schichtung

| Store | Pfad | Inhalt | Wird gelöscht mit |
|---|---|---|---|
| Projekt-Store | `<Projekt>/brain_v3/embeddings.db` | sqlite-vec Vektoren + Units | Projekt |
| Projekt-Store | `<Projekt>/brain_v3/state.db` (Phase 4) | Timeline, Cuts, Klick-Roh-Log | Projekt |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\weights.db` (Phase 3) | Gelernte Achsen-Gewichte | App-Reset |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\patterns.db` (Phase 3) | Profil-Korrelationen | App-Reset |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\embedding_cache.db` ✓ | Hash → Embedding-Lookup | App-Reset |
| Hirn-Store (Files) | `%APPDATA%\PB_Studio\brain_v3\embeddings\<media_type>\<model>__<ver>\<2hex>\<hash>.npy` ✓ | Physische Embedding-Files | App-Reset |

**Konsequenz:** Lerneffekte überleben Projekt-Löschungen.
Embedding-Cache ermöglicht ~0 s Re-Import bekannter Dateien projektübergreifend.
**V3-Pfade kollidieren NICHT mit V1/V2** — separate Subfolder.

---

## V1/V2/V3 Trennung (Plan-Doc 02 #24)

| Aspekt | V1 (`brain_service.py`) | V2 (`brain_v2/`) | V3 (`brain_v3/`) |
|---|---|---|---|
| Code-Namespace | `services.brain_service` | `services.brain_v2.*` | `services.brain_v3.*` |
| DB-Pfad | App-DB | App-DB (eigene Tables) | `%APPDATA%\PB_Studio\brain_v3\` + projekt |
| UI | bestehend | `ui/studio_brain/brain_v2_tab.py` | neu (Phase 5) |
| Algorithmus | Read-only Audit | Memory + α/β (2D) | Beta-Bernoulli mit Hierarchical Backoff (102 Buckets/Klick) |
| Embeddings | nein | nein | CLAP + SigLIP-2 |
| Reranker | nein | nein | ja (Phase 4) |
| Status für V3 | refactor erlaubt + Live-Verify | refactor erlaubt + Live-Verify | aktiv |

---

## Repository-Pattern (strikt)

`sqlite-vec` und `sqlite3` werden **ausschließlich** in
`services/brain_v3/storage/` importiert. Alle anderen V3-Module
(audio/, video/, brain-core in Phase 3, reranker in Phase 4)
greifen über das Repository-Interface zu.

```text
brain_v3/audio/            ──┐
brain_v3/video/              │  Konsumenten:
brain_v3/(future) brain/     │  → kein direkter sqlite3-Import
brain_v3/(future) reranker ──┘  → nur Repository-API

brain_v3/storage/embedding_repository.py    ←── einziger sqlite_vec.load()-Call
brain_v3/storage/embedding_cache.py         ←── einzige Index-DB-API
brain_v3/storage/sqlite_init.py             ←── PRAGMA + Connection-Open
```

**Begründung:** Falls sqlite-vec später durch LanceDB / Postgres
ersetzt werden muss, ist Migration auf das storage/-Verzeichnis begrenzt.

---

## Inferenz-Pfade (Phase 0 verifiziert)

```text
Audio:    PyTorch 1.12.1+cu113 → CLAP Audio-Tower      → 512-dim FP32
                                  742 MB allocated, 808 MB reserved
Video:    PyTorch 1.12.1+cu113 → SigLIP-2 Vision       → 768-dim FP32
                                  AutoImageProcessor (NICHT AutoProcessor)
                                  batch=8: 758 MB reserved
Subtrack: librosa + scipy + numpy                       CPU-only
Storage:  sqlite3 + sqlite-vec                          CPU-only
Render:   ffmpeg + NVENC (Pascal H.264 / HEVC 8-bit)    separater Pfad
```

**GPU-Coordination:** `services/brain_v3/gpu_serializer.GpuSerializer` ✓
ist V3-eigener Threading + Asyncio-Lock mit auto-`empty_cache()` beim
Release. App-globaler Default via `get_default_serializer()`. CLAP- und
SigLIP-Embedder nutzen ihn standardmäßig.

**Plan-Doc 02 #21:** Coexistenz CLAP+SigLIP-2 ist VRAM-mäßig möglich
(Spike: 1178 MB reserved zusammen). Sequenzieller Lifecycle ist
**Defensive, nicht zwingend** — Lock bleibt für Demucs/RAFT/NVENC-Coexistenz.
