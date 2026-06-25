# Audio V2 Reconcile Plan

Plan ID: `AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17`
Status: `approved-for-planning`
Date: 2026-05-20

> **Cross-Plan-Awareness — OTK-021 / Plan C update 2026-06-14:**
>
> `GLOBAL-STORAGE-PROVENANCE-2026-05-19` may proceed under OTK-021 after user
> prerequisite waiver `D-063`. Audio-V2 is now agent-live-verified-complete, but
> OTK-019 deferred gate `DG-001` remains active: full 4h model-pipeline,
> human/QMediaPlayer proxy playback acceptance, and real Demucs+Video
> coexistence must be completed before fixed/release status. Audio-V2 storage
> paths stay stable; Plan C must use adapter/provenance mapping, not hidden V2
> path rewrites.

## Goal

Rette die verwertbare Arbeit aus `sandbox/audio-analysis-v2`, ohne den alten Branch zu mergen und ohne GUI-/Tab-Drift in den aktuellen Branch zu tragen.

## Hard Rules

- Kein Branch-Merge von `sandbox/audio-analysis-v2`.
- Keine untracked Runtime-Artefakte uebernehmen.
- Keine Test-Loeschungen aus dem Sandbox-Diff uebernehmen.
- Keine GUI-Widgets aktivieren, bis die Pipeline fachlich portiert und getestet ist.
- Jede Portierung erfolgt als kleine Task mit gezielten Tests.
- Bei Konflikt mit Video-Pipeline-, LLM- oder Storage-Provenance-Plan stoppen.

## Source Branch Facts

Branch:
- `sandbox/audio-analysis-v2`
- HEAD: `6f414dd2deb412ce1d5ce38c96279c732371731c`

Dirty Sandbox:
- `_sandbox_meta/plan.md` ist lokal geaendert.
- Viele untracked Runtime-Artefakte unter `hjgj/storage/keyframes/`, `hjgj/storage/proxies/`, `hjgj/storage/stems/`.
- Lokale Settings/Projekt-Metadaten sind untracked.

Merge Risk:
- `merge-tree` gegen aktuellen Branch meldet Konflikt in `services/perf_watchdog.py`.
- Der Sandbox-Diff wuerde viele heutige Tests als geloescht anzeigen, weil der Branch alt ist. Diese Deletions sind nicht zu uebernehmen.

## Port Buckets

### Bucket A - Safe Core Candidates

Diese Dateien koennen zuerst einzeln portiert werden, weil sie neue Module sind und wenig bestehende Flaeche anfassen:

- `services/audio_pipeline/context.py`
- `services/audio_pipeline/checkpoint.py`
- `services/audio_pipeline/vram_guard.py`
- `services/audio_pipeline/stem_cache.py`
- `services/audio_pipeline/cleanup.py`
- `services/audio_pipeline/__init__.py`

Tests:
- `tests/test_services/test_pipeline_context.py`
- `tests/test_services/test_pipeline_checkpoint.py`
- `tests/test_services/test_vram_guard.py`
- `tests/test_services/test_stem_cache.py`
- `tests/test_services/test_cleanup_policy.py`

### Bucket B - Orchestrator/Stages Candidates

Nur nach Bucket A:

- `services/audio_pipeline/orchestrator.py`
- `services/audio_pipeline/stages.py`
- `services/audio_pipeline/migration.py`
- `services/audio_pipeline/auto_save_scheduler.py`

Tests:
- `tests/test_services/test_audio_pipeline_module.py`
- `tests/test_services/test_pipeline_orchestrator.py`
- `tests/test_services/test_pipeline_stages.py`
- `tests/test_services/test_pipeline_resume_after_crash.py`
- `tests/test_services/test_pipeline_gpu_lock_serialization.py`
- `tests/test_services/test_migration_stem_pipeline_status.py`
- `tests/test_services/test_auto_save_scheduler.py`

### Bucket C - Service Adapter Candidates

Nur nach Bucket A/B und nur per hunk review:

- `services/stem_router.py`
- `services/av_pacing_service.py`
- `services/beat_analysis_service.py`
- `services/key_detection_service.py`
- `services/structure_detection_service.py`
- `services/analysis_status_service.py`
- `services/project_manager.py`
- `workers/audio_analysis.py`
- `workers/registry.py`

Nicht blind uebernehmen:
- `services/perf_watchdog.py` wegen Merge-Konflikt.
- `ui/controllers/audio_analysis.py` wegen aktueller UI-/Controller-Drift.

### Bucket D - UI Candidates

Erst nach Pipeline-Core:

- `ui/widgets/pipeline_progress_panel.py`
- `ui/widgets/project_save_button.py`
- `tests/ui/test_pipeline_progress_panel.py`
- `tests/ui/test_save_button_click_persists.py`

Regel:
- Nicht in Workspaces einhaengen.
- Kein Toolbar-/Tab-Wiring ohne eigene UI-Task und Screenshot-/Live-Smoke.

## Explicit Rejects For Direct Port

Nicht portieren:
- Runtime-Artefakte unter `hjgj/storage/**`.
- `_sandbox_meta/app_data/**`.
- `pb_project_meta.json`.
- Diff-Deletions von aktuellen Tests.
- GUI-Wiring aus altem Branch ohne aktuelle Ziel-Datei.

## Task Order

### P0 - Freeze And Snapshot

1. Sandbox-HEAD, dirty state und untracked counts dokumentieren.
2. Liste der portierbaren Dateien festhalten.
3. Vault-Mirror aktualisieren.
4. Keine Code-Dateien im Haupttree aendern.

Definition of Done:
- Reconcile-Plan committed.
- Registry zeigt diesen Plan als aktiven Planungsfokus.
- Vault-Mirror existiert.

### P1 - Port Bucket A Core

1. Tests fuer Bucket A aus Sandbox uebernehmen.
2. Core-Module minimal uebernehmen.
3. Tests rot/gruen dokumentieren.
4. Keine UI-Dateien anfassen.

Definition of Done:
- Bucket-A-Tests gruen.
- `py_compile` fuer neue Module gruen.
- Kein Runtime-Artefakt im Repo.

### P2 - Port Bucket B Orchestrator

1. Orchestrator/Stages/Migration/Scheduler test-first portieren.
2. GPU-/VRAM-Regeln gegen GTX 1060 pruefen.
3. Keine Worker-Wiring-Aktivierung.

Definition of Done:
- Orchestrator-Tests gruen.
- Keine Live-Pipeline-Behauptung ohne echte Medien.

### P3 - Port Bucket C Service Adapters

1. Jeden bestehenden Service einzeln diffen.
2. Nur notwendige Hunks portieren.
3. Konflikte mit Video-Pipeline/Storage/LLM stoppen.

Definition of Done:
- Adapter-Tests gruen.
- Bestehende relevante Tests bleiben gruen.

### P4 - UI Proposal Gate

1. UI-Widgets nur als isolierte Widgets pruefen.
2. Kein Workspace-Wiring.
3. Separate UX-Entscheidung fuer Pipeline-Status und Save-Button einholen.

Definition of Done:
- Widget-Tests gruen.
- Keine aktive GUI-Aenderung ohne User-Freigabe.

### P5 - Live Pipeline Verification

1. Mit echtem Audio-Testfile laufen lassen.
2. Logs pruefen.
3. GPU/VRAM beobachten.
4. Erst nach User-Live-Bestaetigung Status erhoehen.

Definition of Done:
- Kein `fixed` ohne User-Live-Bestaetigung.

## Current Next Task

`P0 - Freeze And Snapshot`.

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-018` on 2026-06-09.

- Original plan: `AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17`
- Original open work: P0 Freeze And Snapshot before Audio-V2 port; sandbox branch dirty/old, direct merge forbidden.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.
