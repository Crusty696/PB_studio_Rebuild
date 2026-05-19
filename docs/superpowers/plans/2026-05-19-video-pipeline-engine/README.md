---
plan_id: VIDEO-PIPELINE-ENGINE-2026-05-19
slug: video-pipeline-engine
created: 2026-05-19
status: draft-approved-for-planning
authored_by_user_at: 2026-05-19
vault_decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-045-video-pipeline-engine.md
NOT_TO_CONFUSE_WITH:
  - AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17
  - LLM-BACKEND-PLATFORM-2026-05-19
  - 2026-05-04-brain-v3-nvidia-plan
  - 2026-05-09-schnitt-workspace-redesign
  - 2026-05-13-schnitt-usability-wiring-rebuild
---

# Video-Pipeline-Engine — Implementation Plan

> **EINDEUTIGE PLAN-ID:** `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Pflicht-Tag in Commits / Vault / Tests / Skeptic-Reports.

**Ziel:** DAG-orchestrierte Video-Analyse-Pipeline analog Audio-V2:
- Decoder-Layer (Multi-Format)
- Scene-Detect + Keyframe-Extraction
- SigLIP-Vision-Embeddings (Brain-V3-Coexistenz)
- RAFT Optical-Flow
- VLM-Captioning (Hook auf Plan B Backend)
- Cross-Modal-Sync mit V2-Audio-Outputs
- Proxy-Generation fuer UI-Editing
- Vollstaendigkeits-Garantie (max-Luecke 2 s) auch bei 4 h Video
- Resume-Checkpoint, Dedup

**Hartregeln** (D-040 / D-041 / D-042 / D-045):

- GTX 1060 / CUDA 11.3 only
- Nur User-autorisierte Aenderungen
- Vault pro Sub-Schritt
- Caveman ultra/full
- `status: fixed` nur User
- TDD pro Task

**Tech-Anker:**

- Python: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`
- Vault-Mirror: `wiki/synthesis/plan-video-pipeline-engine-2026-05-19.md`
- Test-Datensatz: Solo_Natur (kurze Clips). 4 h Video: synthetisch geloopt + echte Datei spaeter.

---

## Architektur-Kurzform

```
PB Studio
├── services/video_pipeline/
│     ├── orchestrator.py             VideoAnalysisPipeline (QObject + Signals)
│     ├── stages/
│     │   ├── decode.py                Multi-Format-Decoder
│     │   ├── scene_detect.py          PySceneDetect-Wrapper
│     │   ├── keyframe_extract.py      Pro-Szene + Sample-Pattern
│     │   ├── siglip_embed.py          Vision-Embeddings
│     │   ├── raft_motion.py           Optical-Flow
│     │   ├── vlm_caption.py           Hook -> services/llm (Plan B)
│     │   ├── proxy_gen.py             FFmpeg-Encoder
│     │   └── cross_modal.py           AV-Sync mit V2-Audio
│     ├── primitives/
│     │   ├── frame_sampler.py
│     │   ├── stream_hasher.py
│     │   ├── coverage_guard.py
│     │   ├── resume_checkpoint.py
│     │   └── gpu_lock_aware.py        read-only pynvml + V2-Lock-Respekt
│     └── storage.py                   storage/video_analysis/<track_id>/
├── ui/widgets/
│     └── video_analysis_status_panel.py
└── %APPDATA%/PBStudio/storage/video_analysis/
        └── <track_id>/
            ├── scenes.json
            ├── keyframes/
            ├── embeddings.npy
            ├── motion.json
            ├── captions.json
            ├── proxy.mp4
            └── checkpoint.json
```

---

## Phasen-Reihenfolge (Tier-Mapping wie Plan B)

| Tier | Inhalt | Doc-Files |
|---|---|---|
| **1 Foundation** | DB-Tabellen, Recherche-Modelle, Quality-Profiles | 01, 02, 03 |
| **2 Building-Blocks** | Decoder, Hasher, Sampler, Scene-Wrapper, Keyframe-Selector, Proxy, Coverage, Resume, GPU-Lock-Awareness | 10, 11, 12, 13, 14, 15, 16, 17, 18 |
| **3 Workspace + Services** | Orchestrator, SigLIP-Service, RAFT-Service, VLM-Service, Scene-Service, Keyframe-Service, Proxy-Service, Status-Panel, Trigger-UI, Cross-Modal | 30, 31, 32, 33, 34, 35, 36, 37, 38, 39 |
| **Caller-Migration** | `services/video_analysis_service.py` umstellen | 40, 41, 42 |
| **4 Service-Coverage** | Tests Services ≥ 85 % | 50 |
| **5 Controller-Coverage** | Tests Controllers ≥ 85 % | 51 |
| **6 Test-Infra** | Mock-Decoder, In-Memory-DB, GPU-Stub | 60 |
| **Cross-Cutting** | Errors, Logs, 4h-Video, Disk-Budget, FFmpeg-Lizenz | 70-74 |
| **Verifikation** | Live-Verify | 90, 99 |

---

## Phasen-Datei-Verzeichnis

### Tier 1 — Foundation
- [01_DB_VIDEO_TABLES.md](01_DB_VIDEO_TABLES.md)
- [02_RESEARCH_VIDEO_MODELS.md](02_RESEARCH_VIDEO_MODELS.md)
- [03_QUALITY_PROFILES_VIDEO.md](03_QUALITY_PROFILES_VIDEO.md)

### Tier 2 — Building-Blocks
- [10_VIDEO_DECODER_PRIMITIVE.md](10_VIDEO_DECODER_PRIMITIVE.md)
- [11_VIDEO_STREAM_HASHER.md](11_VIDEO_STREAM_HASHER.md)
- [12_FRAME_SAMPLER.md](12_FRAME_SAMPLER.md)
- [13_SCENE_DETECT_PRIMITIVE.md](13_SCENE_DETECT_PRIMITIVE.md)
- [14_KEYFRAME_SELECTOR.md](14_KEYFRAME_SELECTOR.md)
- [15_PROXY_GENERATOR.md](15_PROXY_GENERATOR.md)
- [16_COVERAGE_GUARD.md](16_COVERAGE_GUARD.md)
- [17_RESUME_CHECKPOINT_VIDEO.md](17_RESUME_CHECKPOINT_VIDEO.md)
- [18_GPU_LOCK_AWARENESS.md](18_GPU_LOCK_AWARENESS.md)

### Tier 3 — Workspace + Services
- [30_VIDEO_PIPELINE_ORCHESTRATOR.md](30_VIDEO_PIPELINE_ORCHESTRATOR.md)
- [31_SIGLIP_VISION_EMBED_SERVICE.md](31_SIGLIP_VISION_EMBED_SERVICE.md)
- [32_RAFT_MOTION_SERVICE.md](32_RAFT_MOTION_SERVICE.md)
- [33_VLM_CAPTION_SERVICE.md](33_VLM_CAPTION_SERVICE.md)
- [34_SCENE_DETECT_SERVICE.md](34_SCENE_DETECT_SERVICE.md)
- [35_KEYFRAME_EXTRACT_SERVICE.md](35_KEYFRAME_EXTRACT_SERVICE.md)
- [36_PROXY_GEN_SERVICE.md](36_PROXY_GEN_SERVICE.md)
- [37_VIDEO_ANALYSIS_STATUS_PANEL.md](37_VIDEO_ANALYSIS_STATUS_PANEL.md)
- [38_USER_TRIGGERS_AND_QUEUE_VIDEO.md](38_USER_TRIGGERS_AND_QUEUE_VIDEO.md)
- [39_CROSS_MODAL_AV_ALIGNMENT.md](39_CROSS_MODAL_AV_ALIGNMENT.md)

### Caller-Migration
- [40_CALLER_MIGRATION_INVENTORY.md](40_CALLER_MIGRATION_INVENTORY.md)
- [41_CALLER_MIGRATION_SERVICES.md](41_CALLER_MIGRATION_SERVICES.md)
- [42_CALLER_MIGRATION_UI.md](42_CALLER_MIGRATION_UI.md)

### Tier 4-6 — Tests + Infra
- [50_TESTS_SERVICES.md](50_TESTS_SERVICES.md)
- [51_TESTS_CONTROLLERS.md](51_TESTS_CONTROLLERS.md)
- [60_TESTS_INFRA_MOCKS.md](60_TESTS_INFRA_MOCKS.md)

### Cross-Cutting
- [70_ERROR_SURFACE_VIDEO.md](70_ERROR_SURFACE_VIDEO.md)
- [71_OBSERVABILITY_VIDEO.md](71_OBSERVABILITY_VIDEO.md)
- [72_LONG_FORM_4H_VIDEO.md](72_LONG_FORM_4H_VIDEO.md)
- [73_DISK_BUDGET_VIDEO.md](73_DISK_BUDGET_VIDEO.md)
- [74_DECODER_LICENSE.md](74_DECODER_LICENSE.md)

### Verifikation
- [90_LIVE_VERIFY.md](90_LIVE_VERIFY.md)
- [99_OPEN_QUESTIONS.md](99_OPEN_QUESTIONS.md)

---

## Pflicht-Regeln pro Sub-Task

1. **Vault-Sync** sofort nach jedem Sub-Step (log.md Zeitstempel).
2. **TDD** RED → GREEN → REFACTOR.
3. **Commit-Format:** `video-pipe: <was>` + Body-Line `Plan: VIDEO-PIPELINE-ENGINE-2026-05-19`.
4. **GPU-Lock-Awareness:** vor GPU-Use `gpu_lock_aware.acquire()` (read-only pynvml-Probe).
5. **0 Overlap mit V2** — keine Audio-Stages, V2-Outputs nur lesen.

## Globaler Erfolgs-Test

User importiert Video, klickt "Alle Analysen", Pipeline laeuft sequentiell (Scene → Keyframes → SigLIP → RAFT → VLM → Cross-Modal), Status-Panel zeigt Fortschritt, Coverage-Garantie ≥ 99.5 %, Proxy fuer UI-Editing erstellt, Crash-Recovery via Resume-Checkpoint. Bei 4 h Video Vollstaendigkeit gegeben.
