---
title: PB Studio Rebuild — Architektur- und Datenfluss-Bericht
date: 2026-05-23
author: Claude (Opus 4.7 1M) im Caveman-Mode
scope: Komplett-Scan aller Bereiche und Funktionen
status: draft
language: de
---

# PB Studio Rebuild — Architektur- und Datenfluss-Bericht

## 0. Scope und Ehrlichkeits-Hinweis

Stand: **2026-05-23**. Branch: `feat/video-pipeline-engine-2026-05-19`.

**Scan-Tiefe ehrlich.** Repo enthält ~1000+ Quelldateien (53 in `services/`, 192 in `ui/`, 27 in `workers/`, 46 in `scripts/`, 1224 in `tests/`). "Jede einzelne Funktion in jedem Detail" sprengt jeden lesbaren Rahmen. Dieser Bericht liefert:

- **Modul-Ebene**: Datei + Zweck + Hauptklassen.
- **Schnittstellen**: Public-API, Signals/Slots, Service-Calls.
- **Daten**: Input/Output-Formate, DB-Tabellen, Datei-Pfade.
- **End-to-End-Fluss**: vom App-Start bis zum gerenderten Video.

**Nicht enthalten**: Implementierungs-Details jeder Hilfsfunktion, Edge-Cases, exakte Algorithmen-Mathematik. Drill-Down pro Modul auf Anfrage.

Methode: 6 parallele Explore-Agents pro Bereich. Output zusammengeführt + verdichtet.

---

## 1. App-Start und Verdrahtung

### 1.1 Entry-Point

- **Hauptdatei**: `main.py:1625` (`if __name__ == "__main__": main()`).
- **Shell-Wrapper**: `start_pb_studio.py` (setzt Env-Vars, ruft `main.py`).
- **main()-Funktion**: `main.py:1257+`.

### 1.2 Start-Sequenz (Reihenfolge)

```
main.py:1257  def main()
├─ .env laden (dotenv)
├─ OpenMP/CUDA-Env-Fixes (KMP_DUPLICATE_LIB_OK, OMP_NUM_THREADS)
├─ DLL-Pfade injizieren (NVIDIA + torch)
├─ CUDA Force-Init (torch.cuda.get_device_name)
├─ QApplication() erstellen
├─ Stylesheet laden (resources/styles.qss)
├─ PBSplashScreen() anzeigen
├─ Base.metadata.create_all(engine)        ← DB-Tabellen
├─ init_db() (Alembic-Migrationen, SYNCHRON, Cycle-14-Hotfix)
├─ PBWindow() konstruieren
├─ window.showMaximized()
├─ QTimer.singleShot(500, final_init)      ← Heavy-Ops verzoegert
└─ app.exec()                              ← Event-Loop
```

Kritisch: **alle DB-Ops vor PBWindow**. Migrationen synchron — sonst Race-Conditions im UI-Boot.

### 1.3 Config

Verzeichnis `config/`:

- `enrichment_rules.yaml` — Audio-Context-Regeln.
- `mood_anchors.npz` + `.yaml` — Mood-Vektor-DB fuer SigLIP-Matching.
- `pacing_rules.yaml` — Schnitt-Entscheidungsregeln.
- `pacing_weights/*.yaml` — Gewichte pro Pacing-Profil.

`.env`-Defaults: `PB_STUDIO_ENABLE_VERSION_CHECK=0`, `PB_STUDIO_ENABLE_SETUP_WIZARD=1`, `CUDA_MODULE_LOADING=LAZY` (GTX-1060-Pflicht).

### 1.4 Datenbank

- **Engine**: `database/session.py:EngineProxy` → `sqlite:///{PROJECT}/pb_studio.db`.
- **ORM**: SQLAlchemy.
- **Migrations**: Alembic in `database/alembic/`, `database/migrations.py:init_db()`.

**Haupt-Tabellen** (`database/models.py`):

| Tabelle | Zweck | Wichtige Spalten |
|---|---|---|
| `projects` | Projekt-Metadaten | name, path, fps, resolution, deleted_at |
| `audio_tracks` | Audio-Datei + Analyse | file_path, bpm, stem_*_path, mood, genre, harmonic_tension |
| `video_clips` | Video-Datei + Analyse | file_path, duration, scenes, embeddings_path, motion_path |
| `beatgrid` | Beat-Grid pro Track | beat_positions (JSON), energy_per_beat, stem_weighted_energy |
| `waveform_data` | Waveform-Cache | waveform_json, duration |
| `timeline_entries` | Schnitt-Plan | track, media_id, start_time, end_time, source_start, locked |
| `pacing_blueprints` | Pacing-Run-Snapshot | cut_points, decisions |
| `analysis_status` | Ready-Flags | audio_ready, video_ready, completion_ts |
| `mem_decision` | Einzelschnitt-Entscheidung (RL) | rationale, contribs, reward |
| `mem_learned_pattern` | Gelernte Muster | fingerprint, confidence |
| `mem_user_feedback_event` | User-Bewertungen | rating, annotation |
| `struct_clip_tags` | Szenen-Tags (Role/Mood/Bucket) | role, mood, bucket |
| `struct_style_bucket` | Stil-Bucket-Cluster | bucket_id, members |
| `struct_compat_edge` | Kompatibilitaets-Graph | a, b, cosine |

Soft-Delete-Pattern (deleted_at nullable). **Keine CASCADE auf Kind-Tabellen** (Bug B-186 bekannt).

**Vektor-DB**: separates `clip_embeddings`-Schema in `services/vector_db_service.py` (SQLite-basiert mit BLOB-Embeddings, KEIN FAISS/LanceDB). Brain V3 nutzt zusaetzlich `brain_v3/state.db` mit FTS5.

### 1.5 Storage-Pfade

```
storage/
├─ backups/        Projekt-Backup-ZIPs
├─ stems/          Demucs-Outputs: {audio_id}_{vocals|drums|bass|other}.wav
├─ proxies/        Low-Res H.264: {video_id}_proxy_h264.mp4
├─ keyframes/      Extracted PNGs: {video_id}_kf_{frame:04d}.png
└─ enricher/       Zwischenergebnisse (JSONs)
```

Brain-V3-Embeddings landen in **Projekt-Root**, NICHT in storage/: `{project_path}/brain_v3/embeddings.db`.

### 1.6 Globale Singletons

| Service | Klasse | Quelle |
|---|---|---|
| Task-Dispatcher | `GlobalTaskManager.instance()` | `services/task_manager.py:81` |
| Modell-Manager (VRAM-Lock) | `ModelManager.instance()` | `services/model_manager.py` |
| Ollama-Client | `OllamaService.get()` | `services/ollama_service.py` |
| Brain-V3-Service | `BrainV3Service` | `services/brain_v3/brain_v3_service.py` |
| Brain-Store | `BrainStore` | `services/brain_v3/storage/brain_store.py` |

GPU-Locks: `GPU_LOAD_LOCK` + `GPU_EXECUTION_LOCK` (RLock) serialisieren VRAM-Ops auf GTX 1060.

### 1.7 Packaging

- **Tool**: PyInstaller + NSIS.
- `installer/build_installer.bat` orchestriert Build.
- `pb_packaging/__init__.py` + `bundle_hooks.py` liefern Custom-Hooks fuer torch/ffmpeg.
- `installer/pre_cache_models.py` laedt KI-Modelle vorab (offline-Installer).
- Output: `dist/pb_studio_setup_v0.5.0.exe`.

---

## 2. Services-Inventar (`services/`)

53 Top-Level-Dateien + Subdirs. Hier die wichtigsten:

### 2.1 Audio-Stack

| Datei | Zweck | Schluessel-API |
|---|---|---|
| `audio_service.py` | Zentrale Audio-Analyse, Pro-Track-Lock (B-143 Refcount) | `AudioAnalyzer`, `track_lock()` |
| `beat_analysis_service.py` | Beat-Tracking via librosa/essentia | `BeatAnalysisService` |
| `key_detection_service.py` | Tonart (Chroma) | `detect_key()` |
| `audio_classify_service.py` | Mood/Genre (essentia) | `AudioClassifyService` |
| `structure_detection_service.py` | Intro/Buildup/Drop/Outro | `StructureDetectionService` |
| `onset_rhythm_service.py` | Percussive Onsets + Rhythm | `OnsetRhythmService` |
| `spectral_analysis_service.py` | 8-Band-Spektral-Hash | `SpectralAnalyzer` |
| `lufs_service.py` | Loudness-Metering (FFmpeg) | `measure_lufs()` |
| `ai_audio_service.py` | Stem-Separation (Demucs), Ducking, Freq-Analyse | `StemSeparator`, `AutoDucker`, `FrequencyAnalyzer` |

### 2.2 Video-Stack

| Datei | Zweck |
|---|---|
| `video_service.py` | Proxy-Mgmt + FFmpeg-Wrap, per-Proxy-Lock (B-156) |
| `video_analysis_service.py` | 3-Schritt-Pipeline: SceneDetect + RAFT-Motion + SigLIP-Embed |
| `video_pipeline/` | Stage-Architektur fuer asynchrone Batch-Analyse |
| `video_analysis_service_moondream.py` | Vision-Captioning (Moondream2 via Ollama) |
| `vector_db_service.py` | SQLite-Vector-DB-Wrapper (Cosine-Suche via NumPy) |

### 2.3 Brain / Pacing / Memory

| Modul | Zweck |
|---|---|
| `brain_service.py` | Read-only Aggregator, lru_cache, UI-Backing |
| `brain_v2/` | Legacy-Knowledge-Store (Preferences, Reasoner, Indexer) |
| `brain_v3/` | Aktuelle Lernschicht: CLAP-Audio + SigLIP-Video + Reranker, Phase 4 Skeleton |
| `pacing/` | RL-Cut-Auswahl (~30 Dateien): `scorer.py`, `pipeline.py`, `SectionPolicy`, `VariationsBudget`, `PatternAggregator`, `DecisionRecorder` |
| `enrichment/` | RoleClassifier (YAML), MoodAnchorMatcher (SigLIP-Softmax), CompatGraphBuilder |
| `graph/` | D-023 Graph-Service, KNN-Backend, CockpitViewModel |
| `pacing_memory.py` | Legacy-Pacing-Memory (Cycle 13) |
| `feedback_service.py` | User-Feedback-Logger (4-Click-Rating) |

### 2.4 Render / Export / Convert

| Datei | Zweck |
|---|---|
| `export_service.py` | Timeline → MP4 via FFmpeg (concat-demuxer), LUFS-Normalisierung, Stem-Mix, 600s-Timeout |
| `convert_service.py` | Proxy/Master-Konvertierung, NVENC-Detect |
| `auto_edit_worker.py` | Dispatch zu `pacing.pipeline` |

### 2.5 Infra / Health / Errors

| Datei | Zweck |
|---|---|
| `model_manager.py` | Singleton VRAM-Schutz (1 Modell aktiv), `@with_model_lock()` |
| `startup_checks.py` | FFmpeg-Pfad, Ollama-Health, CUDA-Check |
| `model_warmup.py` | Pre-Load KI-Modelle (VRAM-Allokation) |
| `gpu_info.py` | CUDA/GPU-Abfrage |
| `errors.py` | 23 Exception-Klassen (PBStudioError, AudioError, VideoError, GPUError, MLError, ...) |
| `cockpit_orchestrator.py` | Readiness-Checks + Dispatch |
| `backup_service.py` | Projekt-Backup + Recovery |
| `recent_projects.py` | Recent-Files-History |
| `conversation_memory.py` | Ollama-Chat-Turn-History |

### 2.6 Externe Abhaengigkeiten

- **ML/AI**: torch, transformers, CLAP, SigLIP-2, librosa, essentia, demucs, RAFT (Optical Flow).
- **FFmpeg**: ffmpeg + ffprobe via subprocess (Timeout/Cancellation).
- **DB**: SQLAlchemy ORM, Alembic Migrations, sqlite-vec (Brain V3).
- **UI/Threading**: PySide6 (QObject, QThread, Signal), Python threading (RLock).
- **APIs**: Ollama HTTP (Chat, Embeddings, Vision).

---

## 3. UI-Inventar (`ui/`)

192 Dateien, PySide6/Qt. ~60+ QWidget-Klassen, ~30 Signals.

### 3.1 Hauptfenster

**`ui/studio_brain_window.py`**: `StudioBrainWindow(QMainWindow)` — Singleton, hostet 6-7 Tabs.

**Signal**: `timelineNavigationRequested(float)` — Story-Map-Thumbnail-Click weiterleiten (P12).

### 3.2 Studio-Brain-Tabs (Director's Cockpit)

| Tab-Index | Klasse | Zweck |
|---|---|---|
| 0 | `StructureTab` | Szenen-Grid + Inspector, Stil-Buckets, Filter |
| 1 | `MemoryTab` | Pacing-Runs + Patterns + Entscheidungs-Drilldown |
| 2 | `AuditTab` | Per-Run-Replay: Schnitt, Reward-Terme, Alternativen, Budget |
| 3 | `SteerTab` | Audio-Track + Gewichtsprofil + Pin/Boost/Exclude-Listen |
| 4 | `PacingDecisionExplorer` | Decision-Replay + Reward-Breakdown |
| 5 | `GraphCockpitTab` | D-023 Sigma.js Graph-Visualisierung (Lazy-Load) |
| (opt.) | `BrainV2Tab` | Beta-Learning-Surface (Env-Flag) |

**Cross-Tab-Wiring**:
- `MemoryTab.runSelected → AuditTab.select_run`.
- `AuditTab.cutSelected → PacingExplorer.select_decision`.
- `AuditTab.storyMapThumbnailClicked → StudioBrainWindow.timelineNavigationRequested`.

**Services pro Tab**: `BrainService` (read-only DB), `BackupService` (Schutz vor destruktiven Ops), `SteerOverrideQueue` (Singleton, Pins/Boosts/Excludes shared).

### 3.3 Workspaces

| Workspace | Zweck | Key-Klassen |
|---|---|---|
| `SchnittWorkspace` | Auto-Schnitt + Review (3 States: Empty/Loading/Editor) | `SchnittEmptyView`, `SchnittLoadingView`, `SchnittEditorView` |
| `MediaWorkspace` | Import + Analyse Video/Audio (Flip-Switch) | `DraggablePoolView`, `MediaPoolGrid`, `AnalysisStatusPanel` |
| `StemsWorkspace` | Stem-Auswahl + Mixer + Transport | `_OnsetTrack`, `StemTrackWidget` |
| `DeliverWorkspace` | Render + Export (Web/HD/4K Presets) | — |

### 3.4 Dialoge

- `SetupWizard` (Hardware → Models → Download → Finish).
- `ProjectDialog` (NewProject / OpenProject).
- `SettingsDialog` (Shortcut-Editor + Allgemeines).
- `ModelManagerDialog` (Ollama-Modelle).
- `CrashDialog`, `GpuRecoveryDialog`, `StartupCheckDialog`.

### 3.5 Controllers (Business-Logic, MVC)

| Controller | Zweck |
|---|---|
| `SchnittController` | Workspace-States + Worker-Dispatch (Tier-1 B7/B8) |
| `AudioAnalysisController` | Audio-Worker-Wrapper |
| `VideoAnalysisController` | Video-Worker-Wrapper |
| `EditWorkspaceController` | Pacing-Agent-Bridge + Timeline-Edit |
| `ProjectManagementController` | CRUD + Recent-Projects |
| `MediaTableController` | Paging + Model-Binding |

**Signal-Pattern**: Worker.done → Slot → UI-State-Update + DB-Commit.

### 3.6 UI-Daten-Fluss (Beispiel Clip-Selektion)

```
User klickt Clip in StructureTab
  → clipSelected(scene_id) Signal
  → InspectorPanel.populate(scene_id)
  → BrainService.get_scene_details(scene_id)  (SQL)
  → Widget zeigt Role/Mood/Bucket
  → User Rechtsklick → Boost/Exclude
  → SteerOverrideQueue.add_boost(scene_id)
  → SteerTab.pendingChanged → snapshot refresh
```

---

## 4. Agents, Workers, Scripts, Tools

### 4.1 Agents (`agents/`, 6 Dateien)

| Datei | Zweck |
|---|---|
| `base_agent.py` | Abstract-Basis: name, domain, model_id, `process()`. ID-Extraktion mit Keyword-Prefix (B-131 verhindert nackte Zahlen) |
| `orchestrator_agent.py` | Multi-Step-Router: zerlegt Prompts in Vision/Audio/Editor/Pacing-Calls. Whitelist Lese-Tools (B-243) |
| `audio_agent.py` | Domain: audio, bpm, stem, vocals, drums. Ruft analyze_audio, separate_stems, detect_key |
| `vision_agent.py` | Domain: video, clip, szene. Unterscheidet FFprobe vs. Moondream2 |
| `editor_agent.py` | Domain: schnitt, timeline, export, auto_edit |
| `pacing_agent.py` | DJ-Pacing-KI. Axiom: Audio=Master, Video=Sklave, Schnitte auf Beats. Multimodal: RAFT-Motion + SigLIP-Semantik. Detektiert Drops/Breakdowns/Buildups |

### 4.2 Workers (`workers/`, 12 Dateien — QThread/Background)

| Datei | Worker | Zweck |
|---|---|---|
| `base.py` | `CancellableMixin`, `format_user_error()` | Thread-safe Cancel + deutsche Fehlermeldungen (CUDA-OOM, VRAM, DB-Lock) |
| `registry.py` | Command-Pattern | Mapped task_name → Worker-Args; 5 Registrierungen: separate_stems, analyze_audio, analyze_video, create_proxy, auto_edit, export_timeline |
| `audio.py` | `StemSeparationWorker` | Background Stem-Sep mit `GPU_EXECUTION_LOCK` (F-004). Input: track_id |
| `analysis.py` | `AnalysisWorker` | 2-Phase Audio-Analyse: Metadaten (STFT) → KI-Beat (beat_this) |
| `video.py` | `VideoAnalysisWorker` | Frame-Extract + FFprobe-Metadaten. Proxy-First-Strategie |
| `audio_analysis.py` | `BaseAnalysisWorker` | Template fuer spezialisierte Audio-Worker |
| `import_export.py` | `ExportWorker`, `ProxyCreationWorker` | Timeline → FFmpeg (B-116/B-121). Triggert auto_edit_invalidates pacing_cache |
| `edit.py` | `AutoEditWorker` | Phase 3 Auto-Edit + AdvancedPacingSettings + OTIO. Dual-Signal-Overload (B-076) |
| `startup.py` | `StartupCheckWorker` | F-030 System-Check (DB, Torch). Verhindert Main-Thread-Blockade |
| `memory_updater.py` | `MemoryUpdaterWorker` | Batches PatternAggregator (N=20). Triggers nach Feedback / Run-End (B-105) |
| `structure_enrichment.py` | `StructureEnrichmentWorker` | T4.1: RoleClassifier + MoodAnchorMatcher + StyleBucketClusterer (UMAP+HDBSCAN) + CompatGraphBuilder. Mutex Fit-Mode (B-100) |
| `brain_v3_hashing.py` | `BrainV3HashingWorker` | Phase-1-App-Sync: SHA256-Hashes nach Folder-Import. Idempotent |

### 4.3 Scripts (`scripts/`, ~34 Dateien)

Kategorien:

- **Test/Verify**: `phase_e_pipeline_smoke.py`, `phase_e_smoke_boot.py`, `phase_h_workflow_smoke.py`, `verify_settings_migration.py`.
- **GPU/Hardware**: `diagnose_cuda.py` (B-215), `fix_gpu_setup.py`, `setup_py310_gpu.py`, `hardware_diag.py`, PowerShell-Scripts (`cuda_recovery.ps1`, `cuda_tdr_config.ps1`, `sb2_gpu_setup.ps1`).
- **Baseline/Data**: `generate_pacing_baseline.py`, `generate_mood_anchors.py`, `generate_golden_decisions.py`, `generate_test_dj_mix.py`, `build_pacing_truth_set.py`.
- **Batch**: `batch_embed_all_clips.py` (AUD-77: 917 Clips ohne Embeddings), `download_beat_weights.py`, `eval_shot_type_prompts.py`.
- **Brain-V3-Spikes**: `spike_brain_v3_*` (Embedder, GPU-Coexistence, KNN, NVENC-Konflikt, ONNX, Pacing, Performance, Reset).
- **Tuning**: `tune_pacing_reward.py`, `warmup_models.py`, `demo_pacing_v2.py`.

### 4.4 Tools (`tools/gui/`, 17 Dateien)

GUI-Automatisierung via **pywinauto** (UIA-Backend, HiDPI-tauglich):

- Import-Workflows: `gui_audio_import*.py`, `gui_video_import*.py`.
- Navigation: `gui_nav_project.py`, `gui_nav_audio.py`, `gui_nav_material.py`, `gui_switch_material.py`.
- Trigger: `gui_trigger_analysis.py`.
- Inspektion: `debug_gui.py`, `find_material_tabs.py`, `map_gui.py`, `list_all_buttons.py`, `scan_ids.py`, `wait_for_gui.py`.

---

## 5. Tests (`tests/`, ~1224 Dateien)

### 5.1 Top-Level-Struktur

20 Subdirectories:

| Subdir | Inhalt |
|---|---|
| `test_services/` | ~280+ Dateien, ~22k Zeilen — Audio/Video/Brain/Pacing/Export/DB/GPU/Ollama |
| `fixtures/` | 30 Dateien, ~209 MB Test-Daten |
| `integration/` | 9 E2E-Tests |
| `test_ui/` | 8 GUI-Tests (ChatDock, GraphCockpit, Timeline, Pacing-Explorer) |
| `test_database/` | 5 Schema/Migration-Tests |
| `test_agents/` | 6 Agent-Tests |
| `enrichment/` | 8 UMAP/HDBSCAN/Mood/Role-Tests |
| `memory/` | 6 Decision-Recorder/PatternAggregator/Backup-Tests |
| `test_workers/` | 11 QThread-Tests |
| `test_scripts/` | 3 Setup-/Start-Skript-Smoke |
| `test_pipeline/` | 2 Pipeline-Wiring-Tests |
| `test_docs/` | 3 Doku/Governance-Validierung |
| `pacing/` | (leer) |
| `spikes/` | 3 exploratorische Dependency-Spikes |
| `tools/`, `ui/`, `workers/` | Legacy / Umstrukturierung |
| `qa_artifacts/` | Screenshots + Logs aus CI |

### 5.2 Pytest-Marker (pyproject.toml)

```
gui        Display erforderlich (skip -m "not gui")
e2e        End-to-End (skip -m "not e2e")
slow       langsame Tests
spike      exploratorische Dependency-Experimente
live_gpu   echte GPU-Modelle
long_form  lange Videos/Audios (4h)
```

### 5.3 GUI-Tests

- **Framework**: `pytest-qt` mit `pytestmark = pytest.importorskip("pytestqt")`.
- **QApplication**: session-scoped Singleton in `conftest.py` (`qapp` Fixture).
- **Render**: Offscreen via `QT_QPA_PLATFORM=offscreen`.
- Auto-Skip bei fehlendem PySide6.

### 5.4 E2E-Beispiele

| Test | Inhalt |
|---|---|
| `test_full_enrichment.py` | 24 Szenen, 3 Clips, HDBSCAN-Cluster, Alembic-tmp-DB |
| `test_dj_mix_3h.py` | 3h DJ-Mix synthetisch, Memory-Budget ≤ 2 GB RSS, `analyze_onsets_chunked` |
| `test_ollama_chat_dock_e2e.py` | Ollama llama3:8b lokal, pyautogui-GUI |
| `test_golden_run_snapshot.py` | Snapshot-Vergleich gegen Erwartung |
| `test_pacing_bridge_snapshot.py` | Pacing-Pipeline-Snapshot |

### 5.5 Fixtures (`tests/fixtures/`, ~209 MB)

| Ordner | Inhalt |
|---|---|
| `clips_20/` | 20 MP4-Clips (~10 MB jeweils), JSON-Metadaten, Provenance |
| `golden_mix/` | `segment.wav`, `scenario.py`, `expected_decisions.json` |
| `pacing_truth_set.template.json` | Pacing-Wahrheitsmenge |
| `shot_type_truth_set.template.json` | Shot-Type-Wahrheitsmenge |

**Gemeinsame Fixtures** (`conftest.py`): `test_engine` (In-Memory SQLite), `db_session`, `project`, `audio_track`, `video_clip`, `patched_schnitt_engine`.

### 5.6 Coverage

Keine dedizierte `.coveragerc`. Coverage-Integration via externe CI-Skripte (`ci/`), nicht in `pyproject.toml`.

---

## 6. End-to-End-Datenfluss

### 6.1 Diagramm

```
User waehlt Video-Ordner + Audio-Datei
         ↓
[INGEST]          ingest_service.ingest_audio() / ingest_video()
         ↓        → AudioTrack + VideoClip Inserts (DB)
         ↓
[AUDIO-ANALYSE]   ai_audio_service (Demucs Stems) + beat_analysis_service
         ↓        → stem_*_path + Beatgrid (JSON-Arrays)
         ↓
[VIDEO-ANALYSE]   video_pipeline (SceneDetect → SigLIP → RAFT → Captions)
         ↓        → embeddings.npy + Scene.ai_caption + motion.json
         ↓
[VECTOR-DB]       vector_db_service (SQLite, Cosine-Suche)
         ↓        → clip_embeddings (BLOB 1152xFloat32 = 4608 Bytes)
         ↓
[ENRICHMENT]      RoleClassifier + MoodAnchorMatcher + CompatGraphBuilder
         ↓        → struct_clip_tags + struct_style_bucket + struct_compat_edge
         ↓
[PACING/DIRECTOR] pacing.pipeline (Section-Detect, Beat-Map, Clip-Score, RL)
         ↓        → Cut-Plan (List[Dict] mit beat/time/energy/mood_match)
         ↓
[TIMELINE]        timeline_service.apply_auto_edit_segments() (atomar)
         ↓        → timeline_entries Inserts (track, media_id, start/end, source_start, locked)
         ↓
[RENDER]          export_service.export_timeline() (FFmpeg concat-demuxer + LUFS-Mix)
         ↓        → exports/{project_id}/output.mp4
         ↓
[FEEDBACK]        feedback_service → mem_user_feedback_event → RL-Update
```

### 6.2 Schritt-Details

**Ingest** (`services/ingest_service.py`):

- `ingest_audio()` L134: Validate → FFprobe-Probe → DB-INSERT `AudioTrack` (file_path, title, duration, sample_rate, bpm=NULL).
- `ingest_video()` L213: FFprobe → DB-INSERT `VideoClip` (file_path, duration, width, height, fps, codec).

**Audio-Analyse**:

- Stem-Sep: `services/ai_audio_service.py` → Demucs PyTorch, `_gpu_execution_locked()` L39.
- Output-Pfade: `storage/stems/{track_id}_{vocals|drums|bass|other}.wav`.
- Beat-Det: `services/beat_analysis_service.py` → librosa Onset + Tempogram.
- Beatgrid-Datenformat:
  ```python
  beat_positions:        List[float]   # Sekunden
  energy_per_beat:       List[float]   # 0.0–1.0 RMS
  stem_weighted_energy:  List[float]   # Stems-normalisiert
  onset_kick_data, onset_snare_data, onset_hihat_data  # AUD-83
  ```

**Video-Analyse** (Stage-Pipeline):

```
Video → KeyframeExtractStage → ProxyGenStage
      → SigLipEmbedStage     (1152-d, → embeddings.npy)
      → RaftMotionStage      (motion.json)
      → VlmCaptionStage      (Scene.ai_caption JSON)
```

Services: `services/video_pipeline/stages/siglip_embed_service.py`, `services/video_analysis_service_moondream.py`, `services/video_service.py`.

Pfade:
- `VideoClip.embeddings_path → storage/embeddings/{clip_id}/embeddings.npy`
- `VideoClip.motion_path → storage/motion/{clip_id}/motion.json`
- `Scene.keyframe_paths → ["keyframes/0_start.jpg", ...]`
- `Scene.embedding_indices → [42, 43, 44]`

**Vector-Suche** (`services/vector_db_service.py`):

```
Tabelle clip_embeddings:
  video_path TEXT
  scene_index INT
  scene_start, scene_end REAL
  motion_score REAL
  description TEXT
  embedding BLOB (1152 * float32)
```

Query L141–150: Cosine via NumPy. Singleton-Pattern (DB-Lock-Serialisierung).

**Pacing** (`services/pacing/`):

1. `compute_stem_weighted_energy()` → Beat-Energie-Kurve.
2. `detect_sections()` → Verse/Chorus/Breakdown/Drop.
3. `_select_cut_beats_advanced()` → Schnitt-Beats abhaengig von Section + Energy.
4. `_match_video_for_segment()` → Vector-DB-Semantic-Search (Mood/Motion).
5. `record_rl_feedback()` → User-Bewertung → Weight-Update.

Cut-Plan-Format:
```python
[
  {"video_id": 3, "start_beat": 0, "end_beat": 7,
   "start_time": 0.0, "end_time": 3.5,
   "energy_score": 0.65, "mood_match": "energetic"},
  ...
]
```

**Timeline** (`services/timeline_service.py`):

- `apply_auto_edit_segments()` L40: atomar DELETE alt → INSERT neu.
- Lock-aware: `locked=True` Clips respektiert.

`timeline_entries`-Schema:
```
track            "video" | "audio"
media_id         VideoClip.id oder AudioTrack.id
start_time       Timeline-Position (s)
end_time         Timeline-Ende (s)
source_start     Offset im Quell-Video (Schnitt-In)
source_end       Offset im Quell-Video (Schnitt-Out)
crossfade_duration  Ueberblendung (s)
brightness, contrast  Farbe (FFmpeg-Filter)
locked           Boolean
```

**Render** (`services/export_service.py:export_timeline()` L306):

```
Timeline-Eintraege
  → Format-Check (Resolution, FPS, Codec)
  → Preprocessing (H.264 + Standardisierung)
  → Concat-File schreiben
  → ffmpeg -f concat -safe 0 -i concat_list.txt
           -i audio_stem_mix.wav
           -c:v libx264 -preset fast -crf 23
           -c:a aac -b:a 128k
           output.mp4
```

NVENC (`h264_nvenc`) per `get_ffmpeg_bin()` hookbar — aktuell nicht standardmaessig aktiv. Output: `exports/{project_id}/output.mp4`.

**Brain-V3-Lifecycle**:

- Boot: `main.py:293` → `QTimer.singleShot(0, _boot_brain_v3_services)` (nach Show).
- `EmbeddingScheduler` (`main.py:728+`) — async Job-Queue fuer CLAP/SigLIP.
- `BrainStore` (`services/brain_v3/storage/brain_store.py`) — SQLite-Embeddings.
- `GpuSerializer` (`services/brain_v3/gpu_serializer.py`) — GPU-Lock fuer parallele Inferenz.
- `ContextResolver` — Audio/Video-Context aus Embeddings.
- Audio-Embedder: `ClapAudioEmbedder` (`services/brain_v3/audio/audio_embedder.py`).
- Video-Embedder: `Siglip2VideoEmbedder` (`services/brain_v3/video/video_embedder.py`).
- Cache: `EmbeddingCache` (media_hash → embedding) vor Recompute.
- Shutdown: `PBWindow.closeEvent:969+` → `EmbeddingScheduler.request_stop()`.

### 6.3 Persistenz zwischen Sessions

```
{project_path}/
├─ pb_studio.db          SQLAlchemy Main-DB
├─ storage/
│  ├─ stems/             Demucs-Outputs
│  ├─ proxies/           Low-Res H.264
│  ├─ keyframes/         PNGs
│  └─ enricher/          Zwischenergebnisse
├─ data/vector/
│  └─ embeddings.db      SQLite Vector-DB
├─ brain_v3/
│  └─ embeddings.db      Brain-V3-Store (FTS5 + Embeddings)
└─ exports/
   └─ output.mp4         Render-Output
```

Persistiert: Projekt-Metadaten, AudioTrack (inkl. Stem-Pfade, BPM, Key, Mood), Beatgrid, VideoClip (inkl. Embeddings/Motion-Pfade), Scene, TimelineEntry, Vector-DB, Brain-V3-Store.

---

## 7. Schluessel-Daten und Pfade — Konsolidiert

### 7.1 Datei-Pfade pro Datentyp

| Datentyp | Pfad |
|---|---|
| Haupt-DB | `{project}/pb_studio.db` |
| Stems | `{project}/storage/stems/{audio_id}_{stem}.wav` |
| Proxies | `{project}/storage/proxies/{video_id}_proxy_h264.mp4` |
| Keyframes | `{project}/storage/keyframes/{video_id}_kf_{frame:04d}.png` |
| SigLIP-Embeddings | `{project}/storage/embeddings/{clip_id}/embeddings.npy` |
| RAFT-Motion | `{project}/storage/motion/{clip_id}/motion.json` |
| Vector-DB | `{project}/data/vector/embeddings.db` |
| Brain-V3-Store | `{project}/brain_v3/embeddings.db` |
| Render | `{project}/exports/{project_id}/output.mp4` |
| Backups | `{project}/storage/backups/*.zip` |

### 7.2 Kritische DB-Queries

- `BrainService.get_scenes()` / `.get_tags()` — UI StructureTab.
- `BrainService.get_pacing_runs()` / `.get_learned_patterns()` / `.get_decisions_for_pattern()` — UI MemoryTab.
- `BrainService.get_cut_details(decision_id)` / `.get_alternatives()` — UI AuditTab.
- `BrainService.get_audio_tracks()` — UI SteerTab.
- `TimelineEntry.count(project_id, track='video')` — SchnittWorkspace-State-Decision.

### 7.3 Thread-Safety-Locks

- `GPU_LOAD_LOCK` — Modell-Lade-Phase.
- `GPU_EXECUTION_LOCK` — Inferenz-Phase (B-143 / F-004 / B-156).
- Per-Track-RefCount-Lock — `track_lock()` in `audio_service.py`.
- Per-Proxy-Lock — `video_service.py`.
- Mutex Fit-Mode — `structure_enrichment.py` (B-100 / BUG-6-b).
- Double-Checked-Locking — `GlobalTaskManager.instance()`.

---

## 8. Was dieser Bericht NICHT abdeckt (Ehrlichkeit)

- Implementierungs-Code jeder einzelnen Hilfsfunktion in 1000+ Dateien.
- Exakte Mathematik der Reward-Funktionen, UMAP-/HDBSCAN-Hyperparameter, RAFT-Inferenz-Pipeline.
- Pruefung welche Funktionen tatsaechlich verdrahtet vs. dead-code sind. Fuer Verdrahtungs-Audit: separater Lauf mit `pb-deep-auditor`.
- Live-Verifikation: dies ist Source-Inspection-only. Kein App-Start, kein E2E-Test gefahren.
- Aktive Bugs / aktive Plan-Phase: in `docs/superpowers/PLAN_REGISTRY.md` + `docs/superpowers/ACTIVE_PLAN.md` + Vault `C:\Brain-Bug\projects\pb-studio\wiki\`.
- Performance-Profile: nur strukturell. Echte VRAM-/Laufzeit-Messung waere separater Job.

---

## 9. Verweise

- `AGENTS.md` — Single source of truth fuer Agent-Verhalten.
- `CLAUDE.md` — Projekt-Hartregeln (GPU, Vault, User-Autorisierung).
- `docs/superpowers/PLAN_REGISTRY.md` — Plan-Authority.
- `docs/superpowers/ACTIVE_PLAN.md` — Aktiver Plan.
- Vault: `C:\Brain-Bug\projects\pb-studio\wiki\` (Bugs/Decisions/Synthesen).

---

**Bericht-Ende.** Stand 2026-05-23. Methode: 6 parallele Explore-Agents + manuelle Synthese.
