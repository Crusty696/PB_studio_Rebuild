# PB Studio Source Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Einen sauberen Integrationsbranch herstellen, der aktuelles `origin/main`, die 16 committed OTK-021-Folgecommits, B-549, B-554 und BUG-A enthält, ohne das dirty Originalrepo zu verändern.

**Architecture:** `origin/main` bleibt Basis. Der committed Branch `origin/claude/B-539-cross-project-reuse-by-sha-2026-06-18` wird als zusammenhängende Historie gemergt. B-549 wird aus dem belegten Fremdrepo-Commit rekonstruiert; B-554 und BUG-A werden aus dem klar abgegrenzten Dirty-Diff übernommen. Jede Einheit erhält eigene Tests und eigenen Commit.

**Tech Stack:** Git Worktrees, Python 3.10 `pb-studio`, pytest, PySide6, CUDA 11.3/GTX 1060.

---

### Task 1: OTK-021 committed branch sequence integrieren

**Files:**
- Merge: `origin/claude/B-539-cross-project-reuse-by-sha-2026-06-18`
- Verify: `services/storage_provenance/**`
- Test: `tests/test_services/test_cross_project_reuse.py`
- Test: `tests/test_services/test_manifest_robustness.py`
- Test: `tests/test_services/test_ingest_service.py`

- [ ] **Step 1:** Merge ohne Rebase:

```powershell
git merge --no-ff origin/claude/B-539-cross-project-reuse-by-sha-2026-06-18 -m "merge(OTK-021): consolidate provenance and recovery branch"
```

- [ ] **Step 2:** Konflikte nur anhand beider Commit-Historien auflösen; bei fachlichem Widerspruch stoppen.

- [ ] **Step 3:** Syntax und fokussierte Tests:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m compileall -q services\storage_provenance services\analysis_status_service.py services\ingest_service.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_cross_project_reuse.py tests\test_services\test_manifest_robustness.py tests\test_services\test_ingest_service.py -q
git diff --check HEAD^ HEAD
```

Expected: compile exit 0; focused tests pass; diff-check exit 0.

### Task 2: B-549 Cancel-Fix übernehmen

**Files:**
- Modify: `services/audio_pipeline/context.py`
- Modify: `services/audio_pipeline/orchestrator.py`
- Modify: `services/audio_pipeline/stages.py`
- Modify: `workers/audio_pipeline_v2_worker.py`
- Modify: `tests/test_workers/test_audio_pipeline_v2_worker.py`

- [ ] **Step 1:** Fremdrepo-Commit `0f7fc3e` diffgenau lesen und nur dessen fünf Pfade übernehmen.

- [ ] **Step 2:** Fokus-Test:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_workers\test_audio_pipeline_v2_worker.py -q
```

Expected: alle Tests grün.

- [ ] **Step 3:** Commit:

```powershell
git add services/audio_pipeline/context.py services/audio_pipeline/orchestrator.py services/audio_pipeline/stages.py workers/audio_pipeline_v2_worker.py tests/test_workers/test_audio_pipeline_v2_worker.py
git commit -m "fix(B-549): integrate Audio-V2 cooperative cancellation" -m "Live evidence exists from prior run; consolidated branch regression tests green."
```

### Task 3: B-554 Freeze-/Reload-Fix übernehmen

**Files:**
- Modify: `services/brain_v3/embedding_scheduler.py`
- Modify: `services/brain_v3/video/video_embedder.py`
- Modify: `tests/test_services/test_brain_v3_embedding_scheduler.py`

- [ ] **Step 1:** Dirty Originaldiff exakt übernehmen: lokaler HF-Cache zuerst; persistente Video-/Audio-Embedder; Cache-Unload bei Scheduler-Stop.

- [ ] **Step 2:** Fokus-Test:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_brain_v3_embedding_scheduler.py -q
```

Expected: alle Tests grün, inklusive Ein-Instanz- und Unload-Regressions.

- [ ] **Step 3:** Commit:

```powershell
git add services/brain_v3/embedding_scheduler.py services/brain_v3/video/video_embedder.py tests/test_services/test_brain_v3_embedding_scheduler.py
git commit -m "fix(B-554): reuse SigLIP embedder and prefer local cache" -m "Prior GUI live evidence: 52 clips, one model load, no hang; consolidation tests green."
```

### Task 4: BUG-A Auto-Edit-State-Refresh übernehmen

**Files:**
- Modify: `ui/controllers/edit_workspace.py`
- Test: passende bestehende SCHNITT-Controller-/Empty-State-Tests

- [ ] **Step 1:** Nach Auto-Edit-Abschluss `_schnitt_ws.refresh_state_from_db()` defensiv aufrufen.

- [ ] **Step 2:** Tests:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\ui\test_schnitt_empty_state_preset_runs_pipeline.py tests\ui\test_schnitt_controller_wiring.py -q
```

Expected: alle Tests grün.

- [ ] **Step 3:** Commit:

```powershell
git add ui/controllers/edit_workspace.py
git commit -m "fix(OTK-021): refresh SCHNITT state after Auto-Edit" -m "Prior GUI live evidence exists; consolidation regression tests green."
```

### Task 5: Konsolidierten Stand verifizieren

**Files:**
- Verify only: gesamter Integrationsdiff gegen `origin/main`

- [ ] **Step 1:** Status-/Diff-Prüfung:

```powershell
git status --short --branch
git diff --check origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

- [ ] **Step 2:** Konsolidierte Fokus-Suite:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_cross_project_reuse.py tests\test_services\test_manifest_robustness.py tests\test_services\test_ingest_service.py tests\test_workers\test_audio_pipeline_v2_worker.py tests\test_services\test_brain_v3_embedding_scheduler.py tests\ui\test_schnitt_empty_state_preset_runs_pipeline.py tests\ui\test_schnitt_controller_wiring.py -q
```

Expected: alle ausgewählten Tests grün.

- [ ] **Step 3:** Kein `fixed`-Status ändern. Report/Vault/Handoff mit Branch, Commits, Tests und offenen Live-Gates aktualisieren.

- [ ] **Step 4:** Branch zu `origin` pushen; `main` nicht direkt verändern.
