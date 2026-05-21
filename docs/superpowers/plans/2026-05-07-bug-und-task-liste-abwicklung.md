# Bug- und Task-Liste 2026-05-07 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Subagents are not recommended here because project rules require one sequential task at a time. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Offene Bugs und Tasks aus `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\bug-und-task-liste-2026-05-07.md` in strikter Reihenfolge abarbeiten, ohne Phase-Gates oder `fixed`-Marker zu faelschen.

**Architecture:** Erst Gate- und Live-Verifikationen fuer Brain V3 Phase 1 bis 6, dann pending GUI-Verifikationen, dann aktive nicht-Phase-Bugs, dann Design-Entscheidungen. Jede Codeaenderung bleibt auf den jeweiligen Bug beschraenkt und bekommt eigene Tests, Vault-Eintrag und ehrlichen Status.

**Tech Stack:** Python 3.10, PySide6, SQLite/SQLAlchemy, Brain V3 Services, CUDA `torch==1.12.1+cu113` auf GTX 1060 6 GB, FFmpeg/NVENC, pytest, PowerShell, `tests/gui_harness.py`.

---

## 2026-05-20 Governance Update

Plan-ID: `PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20`

Registry:

- `docs/superpowers/PLAN_REGISTRY.md` fuehrt diesen Plan mit Status `approved-for-implementation`.
- `docs/superpowers/ACTIVE_PLAN.md` setzt diesen Plan als aktiven Fokus.
- Vault-Mirror: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\bug-und-task-liste-2026-05-20.md`.
- Decision: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-049-offene-bugs-tasks-masterplan.md`.

Aktueller naechster Task:

```text
Governance Gate + SCHNITT B-310/B-316..B-320 Reihenfolge pruefen.
```

Audio-V2-Reconcile ist pausiert, nicht geloescht. Keine Audio-V2-Portierung in diesem Masterplan.

## Source Of Truth

**Plan-Aufgabe aus Vault, verbatim:**

`Konkrete offene Tasks aus Plan/Vault`

- `Phase 1 Live-Smoke: App starten, 3 echte Audio + 3 echte Video importieren, V3-DB pruefen.`
- `Phase 1 Re-Import-Smoke: dieselben Files erneut importieren, Hash-Cache-Hit, keine Duplikate.`
- `Phase 2 voller 5-Mix-Smoke: lokale Suche fand nur 3 reale Audiofiles / 2 eindeutige Audio-Hashes.`
- `Phase 2 kompletter 10-Clip-Re-Import-Cache-Hit-Smoke fehlt.`
- `Phase 3/5 realer Klickpfad: Timeline-Cut anklicken, Brain-V3-Popup nutzen, Rating speichern, Stats-Update pruefen.`
- `Phase 5 Lern-Session UI: Audio-/Video-Preview live pruefen.`
- `Phase 6 B-276: echter Renderpfad mit Brain-Inferenz live pruefen.`
- `Phase 6 B-277: GUI-Harness Shutdown ohne Force-Fallback stabilisieren.`
- `User muss Phase-Level-Marker setzen; Agent darf fixed/DONE nicht allein setzen.`

**Aktive offene Bugs aus Vault:**

- `B-175` Re-Import nach Soft-Delete blockiert mit IntegrityError.
- `B-219` WinError 32 Proxy-File-Lock zwischen Pipeline und BatchAnalysis.
- `B-229` `_compute_temporal_bands` per-window normalization defeats timbral evolution.
- `B-231` `analyze_extended` laedt y und STFT doppelt.
- `B-265` GTX 1060 aktuell nicht als CUDA-Device verfuegbar.
- `B-270` EDL export missing `opentimelineio-contrib`.
- `B-277` GUI harness shutdown falls back to force kill.

**Code-Fix liegt vor, Live-Verifikation fehlt:**

- `B-196`, `B-197`, `B-198`, `B-199`
- `B-272`, `B-273`, `B-274`, `B-275`, `B-276`

**2026-05-20 SCHNITT / Pipeline Aktualisierung:**

- `B-310` bleibt `code-fix-pending-live-verification`; voller offizieller SCHNITT-Live-Workflow ist nicht final bestaetigt.
- `B-316` bleibt `open`; Code-Fix und Teil-Live-Test existieren, aber User-Bestaetigung fehlt und B-317 blockiert Default-Verhalten.
- `B-317` ist `fixed` per Commit `90e4e1b` und Live-Test vom 2026-05-20.
- `B-318` ist `fixed`; aktueller HEAD rendert Entry-Dauer, Test + Live-Screenshot/DB-Abgleich vom 2026-05-20 bestaetigen den realen SCHNITT-Pfad.
- `B-319` ist `code-fix-pending-live-verification`; Tests und DB-Integritaetscheck sind gruen, aber ein neuer Auto-Edit-Live-Run wurde nicht ausgefuehrt.
- `B-320` ist `code-fix-pending-live-verification`; Timeline-Video-Clips bekommen gecachtes Thumbnail oder Placeholder, Tests sind gruen, aber realer SCHNITT-Live-Nachtest war durch laufende Hintergrundtasks beim Projektwechsel blockiert.
- `B-321` ist `fixed`; finaler Live-Nachtest 2026-05-21 lief mit vorhandenen Videos fachlich durch: 3 Videos, 3 Szenen, 3 Embeddings; UI blieb 6 Minuten `Responding=True`; 30 Completion-Events wurden auf 9 echte UI-Refreshes + 21 `no table refresh` reduziert; keine Completion-Refresh-Watchdogs, kein Pipeline-Traceback/CRITICAL/QThread-Crash.
- `B-323` ist `code-fix-pending-live-verification`; TaskManagerDock normalisiert Progress/Total vor QProgressBar-Settern, Tests und App-Start-Smoke sind gruen, voller B-321 Video-Pipeline-Live-Test fehlt weiter.
- `B-324` ist `fixed`; stale Proxy-Pfade fallen auf vorhandene Originaldateien zurueck, fehlende Pipeline-Eingabe wirft Fehler statt leeres Erfolgsergebnis, Live-Lauf mit IDs 1-3 erzeugte 3 Szenen/3 Embeddings.
- `B-322` bleibt `code-fix-pending-live-verification`; Agent-Live-Test existiert, User-Bestaetigung fehlt.
- `B-300`, `B-303`, `B-304`, `B-305` bleiben pending-live laut Vault-Status und duerfen nicht als `fixed` behandelt werden.

## Hard Gates

- Phase-Reihenfolge bleibt `0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6`.
- Keine Phase bekommt `fixed` oder `DONE` durch Agent allein.
- Live-Verifikation vor Vault-Status `fixed`.
- `B-310` / SCHNITT-Folgearbeit hat Vorrang vor GPU/Brain/Pipeline-Gates: erst B-310 Live-Gate, dann B-316..B-320 in Bug-Reihenfolge.
- B-229, B-231 und B-175 brauchen Design- bzw. Migrationsentscheidung vor Code.
- B-265 ist Hardware/Windows-State. Kein App-Codefix ohne reproduzierbaren Codefehler.
- CUDA muss vor Phase-2-/Phase-6-GPU-Livepfad aktuell verfuegbar sein.

## File Map

**Plan/Vault:**

- Read: `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
- Read: `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/07_RISKS.md`
- Read: `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/08_VERIFICATION.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\bug-und-task-liste-2026-05-07.md`
- Update after real tests: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-<scope>-2026-05-07.md`
- Update after bug work: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-XXX-<slug>.md`
- Update after commits/product changes: `C:\Brain-Bug\projects\pb-studio\log.md`

**Likely code touch points, only when the matching task reaches code phase:**

- `ui/controllers/import_media.py` for Phase 1/2 import hooks.
- `services/brain_v3/storage/media_hash_registry.py` for Phase 1 DB checks.
- `services/brain_v3/embedding_scheduler.py` for Phase 2 scheduler checks.
- `services/brain_v3/brain_v3_service.py` for Phase 3/5 service behavior.
- `ui/timeline.py` for B-272, B-274, B-275 live checks and future fixes.
- `ui/widgets/brain_v3_learning_dialog.py` for B-273 preview UI.
- `services/convert_service.py` and `services/brain_v3/gpu_serializer.py` for B-276.
- `tests/gui_harness.py` for B-277.
- `database/models.py` and ingest/import service path for B-175.
- `services/video_service.py` for B-219.
- `services/spectral_analysis_service.py` for B-229 and B-231.
- `requirements*.txt` / dependency config for B-270, only after approval to add dependency.

---

## Task 0: Gate-Check Und Working Tree

**Files:**

- Read: `AGENTS.md`
- Read: `docs/superpowers/PLAN_REGISTRY.md`
- Read: `docs/superpowers/ACTIVE_PLAN.md`
- Read: source Vault synthesis and bug files listed above.
- No code change.

- [ ] **Step 1: Quote current task**

Use exact quote:

```text
Phase-/Bug-Abarbeitung aus C:\Brain-Bug\projects\pb-studio\wiki\synthesis\bug-und-task-liste-2026-05-07.md
```

- [ ] **Step 2: Check git state**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected:

```text
Current branch is main or explicitly documented otherwise.
Dirty files are listed before any edit.
```

- [ ] **Step 3: Check phase predecessor status in Vault**

Run:

```powershell
Get-ChildItem -LiteralPath 'C:\Brain-Bug\projects\pb-studio\wiki\synthesis' -Filter '*phase*' | Sort-Object Name | Select-Object Name, LastWriteTime
```

Expected:

```text
Phase 0 is confirmed done. Phase 1+ markers are not changed by agent.
```

- [ ] **Step 4: Stop condition**

If `06_PHASES.md` and a phase blueprint contradict each other, stop and ask user. Do not choose.

---

## Task 0.5: SCHNITT Governance Gate B-310/B-316..B-320

**Files:**

- Read: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-schnitt-b310-2026-05-13.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-310-schnitt-workspace-unusable-half-wired-ux.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-316-schnitt-audio-subtab-missing-metadata-waveform.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-317-schnitt-default-audio-selects-unanalyzed-track.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-318-schnitt-timeline-renders-media-duration-instead-entry-duration.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-319-schnitt-timeline-data-overlap-audio-duplicates-source-mismatch.md`
- Read: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-320-schnitt-timeline-video-clips-missing-thumbnails.md`
- No app-code change in this gate.

- [ ] **Step 1: Quote task**

```text
Governance Gate + SCHNITT B-310/B-316..B-320 Reihenfolge pruefen.
```

- [ ] **Step 2: Check current statuses**

Expected status before code work:

```text
B-310 = code-fix-pending-live-verification
B-316 = open
B-317 = fixed
B-318 = fixed
B-319 = code-fix-pending-live-verification
B-320 = code-fix-pending-live-verification
```

- [ ] **Step 3: Execution order**

Use this exact order:

```text
1. B-310 live verification gate.
2. B-316 if B-310 still blocked by audio metadata/waveform evidence.
3. B-317 default audio selection.
4. B-318 timeline entry duration rendering.
5. B-319 timeline data overlap/source-duration mismatch.
6. B-320 timeline thumbnails.
```

- [ ] **Step 4: Stop condition**

If B-310 can be live-confirmed by the user before code work, do not invent extra B-310 code. If B-316 evidence is already solved but B-317 blocks the visible default, start with B-317.

---

## Task 1: B-265 CUDA Preflight

**Files:**

- Update if result changes: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-265-gtx1060-cuda-unavailable.md`
- No app code change.

- [ ] **Step 1: Quote task**

```text
B-265 | open | GTX 1060 aktuell nicht als CUDA-Device verfuegbar
```

- [ ] **Step 2: Run hardware checks**

Run:

```powershell
Get-PnpDevice -Class Display
nvidia-smi -L
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv
```

Expected:

```text
NVIDIA GeForce GTX 1060 present, status OK, 6144 MiB VRAM visible.
```

- [ ] **Step 3: Run Python CUDA smoke in project env**

Run with the same Python used by app startup:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.device_count()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO_CUDA')"
```

Expected:

```text
torch 1.12.1+cu113, CUDA True, device_count 1, NVIDIA GeForce GTX 1060.
```

- [ ] **Step 4: Status handling**

If CUDA false, stop GPU live tasks. Update B-265 with current evidence and keep `status: open`.

---

## Task 2: Phase 1 Live Import/Re-Import Smoke

**Files:**

- Verify: `ui/controllers/import_media.py`
- Verify: `services/brain_v3/storage/media_hash_registry.py`
- Create/update: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-phase1-import-reimport-2026-05-07.md`
- Update only after live proof: relevant phase synthesis, but do not set phase marker without user.

- [ ] **Step 1: Quote plan task**

```text
Phase 1 Live-Smoke: App starten, 3 echte Audio + 3 echte Video importieren, V3-DB pruefen.
```

- [ ] **Step 2: Read DoD**

Read Phase 1 DoD in:

```text
docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md
```

Acceptance:

```text
Hashes exist in V3 DB, schema fields filled, no duplicate rows on re-import.
```

- [ ] **Step 3: Start app**

Run:

```powershell
python tests\gui_harness.py start --force
python tests\gui_harness.py wait-window --title PB_studio --timeout 45
```

Expected:

```text
Window found. If not found, stop and log exact harness/app log evidence.
```

- [ ] **Step 4: Live import**

In app UI, import exactly:

```text
3 real audio files
3 real video files
```

Acceptance:

```text
Console/log contains Brain V3 hash lines for all 6 files.
No UI crash.
```

- [ ] **Step 5: Inspect V3 DB**

Use `MediaHashRegistry` or sqlite DB inspection. Record:

```text
media_hash count before import
media_hash count after import
short hashes
source paths
media types
```

- [ ] **Step 6: Re-import same files**

Use exact quote:

```text
Phase 1 Re-Import-Smoke: dieselben Files erneut importieren, Hash-Cache-Hit, keine Duplikate.
```

Expected:

```text
Hash-Cache-Hit logs appear.
media_hash count unchanged for same file hashes.
```

- [ ] **Step 7: Vault**

Create/update:

```text
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-phase1-import-reimport-2026-05-07.md
```

Status language:

```text
live verified, if app UI path was really used.
partial / failed, if any import or DB check failed.
```

---

## Task 3: Phase 2 Embedding Live Smoke And Cache-Hit

**Files:**

- Verify: `services/brain_v3/embedding_scheduler.py`
- Verify: `services/brain_v3/storage/embedding_cache.py`
- Verify: `services/brain_v3/audio/audio_embedder.py`
- Verify: `services/brain_v3/video/video_embedder.py`
- Create/update: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-phase2-embedding-reimport-2026-05-07.md`

- [ ] **Step 1: Quote plan task**

```text
Phase 2 voller 5-Mix-Smoke: lokale Suche fand nur 3 reale Audiofiles / 2 eindeutige Audio-Hashes.
```

- [ ] **Step 2: Check dependency**

Phase 1 live import/re-import must be documented. If not, stop.

- [ ] **Step 3: Prepare real media set**

Need:

```text
5 real mix files
10 real clips
```

If fewer files exist locally, stop and ask user for media paths. Do not substitute synthetic files for this live task.

- [ ] **Step 4: Start app and import**

Run:

```powershell
python tests\gui_harness.py start --force
python tests\gui_harness.py wait-window --title PB_studio --timeout 45
```

Then import media in app.

Expected:

```text
EmbeddingScheduler starts.
CLAP/SigLIP jobs complete or cache-hit.
No CUDA OOM on GTX 1060.
```

- [ ] **Step 5: Inspect cache artifacts**

Record:

```text
embedding_cache.db row counts
.npy file count
model_name/model_version for audio/video
job progress log lines
VRAM before/after if available
```

- [ ] **Step 6: Re-import cache hit**

Quote:

```text
Phase 2 kompletter 10-Clip-Re-Import-Cache-Hit-Smoke fehlt.
```

Expected:

```text
Embedding-Cache-Hit logs.
No second inference for unchanged hashes.
Cache count unchanged for identical files.
```

- [ ] **Step 7: Vault**

Create/update:

```text
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-phase2-embedding-reimport-2026-05-07.md
```

Do not set Phase 2 marker to `fixed` or `DONE`.

---

## Task 4: Phase 3/4 Brain Service Live Path

**Files:**

- Verify: `services/brain_v3/brain_v3_service.py`
- Verify: `services/brain_v3/storage/brain_store.py`
- Verify: `services/pacing/pipeline.py`
- Create/update: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-phase3-4-brain-service-2026-05-07.md`

- [ ] **Step 1: Quote plan task**

```text
Phase 3/5 realer Klickpfad: Timeline-Cut anklicken, Brain-V3-Popup nutzen, Rating speichern, Stats-Update pruefen.
```

- [ ] **Step 2: First run service-level smoke**

Run existing focused tests before live UI:

```powershell
python -m pytest tests/test_services/test_brain_v3_brain_store_health.py tests/test_services/test_brain_v3_phase5_widgets.py -q
```

Expected:

```text
All tests pass. If tests fail, stop and diagnose first.
```

- [ ] **Step 3: Run one real Pacing path with Brain V3 enabled**

Use app UI path that creates timeline cuts with Brain V3 service active. Record:

```text
timeline id
cut count
Brain V3 score/rationale presence
pacing latency
fallback logs, if any
```

- [ ] **Step 4: Vault**

Create/update functional test synthesis. If only service tests pass, write `unit/service green, live UI pending`.

---

## Task 5: Phase 5 UI Live Verification And B-273 Gap

**Files:**

- Verify/possibly modify: `ui/timeline.py`
- Verify/possibly modify: `ui/widgets/brain_v3_feedback_popup.py`
- Verify/possibly modify: `ui/widgets/brain_v3_learning_dialog.py`
- Verify/possibly modify: `services/brain_v3/brain_v3_service.py`
- Verify/possibly modify: `services/brain_v3/schemas/brain_v3_schemas.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-272-phase5-timeline-brain-v3-feedback-not-wired.md`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-273-phase5-learning-dialog-preview-missing.md`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-274-phase5-timeline-confidence-bar-missing.md`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-275-startup-interactive-timeline-slow-metacall.md`

- [ ] **Step 1: Quote plan task**

```text
Phase 5 Lern-Session UI: Audio-/Video-Preview live pruefen.
```

- [ ] **Step 2: Verify existing code-fix tests**

Run:

```powershell
python -m pytest tests/test_services/test_brain_v3_phase5_widgets.py tests/test_ui/test_timeline_startup_batching_b275.py -q
python -m py_compile ui\timeline.py ui\widgets\brain_v3_learning_dialog.py ui\widgets\brain_v3_feedback_popup.py
```

Expected:

```text
Tests and py_compile pass before live UI.
```

- [ ] **Step 3: Live feedback popup**

In real app:

```text
Select a real timeline cut.
Open context menu.
Click "Brain V3: Cut bewerten".
Submit each rating path at least once across 1-4 hotkeys or popup.
Open Stats panel.
Confirm total click count changed.
```

Acceptance:

```text
B-272 can move only if popup opens from real timeline and feedback persists.
B-274 can move only if real cut shows confidence bar from real metadata.
```

- [ ] **Step 4: Live learning preview**

In real app:

```text
Open Brain V3 learning session.
Load a sample tied to real project media.
Play audio preview.
Display video preview.
Stop preview.
Close dialog.
```

Acceptance:

```text
Audio and video preview use real paths. No fake preview paths.
```

- [ ] **Step 5: B-273 stop condition**

If `BrainV3Service.learning_session()` still returns `audio_preview_path=None` and `video_preview_path=None` for real app samples, do not mark B-273 fixed. Plan code task:

```text
Add service/data-layer linkage from learning sample cut to real audio/video source path and position.
```

Minimal expected code scope:

```text
services/brain_v3/brain_v3_service.py
services/brain_v3/schemas/brain_v3_schemas.py
tests/test_services/test_brain_v3_learning_session_preview_paths.py
```

- [ ] **Step 6: B-275 startup log check**

After app start, inspect log for slow `MetaCall -> InteractiveTimeline`.

Expected:

```text
No new slow startup MetaCall for InteractiveTimeline after batching.
```

If still present, keep B-275 pending and profile exact receiver path before code.

---

## Task 6: Phase 6 Recovery, NVENC, B-276, B-277

**Files:**

- Verify/possibly modify: `services/brain_v3/storage/backup.py`
- Verify/possibly modify: `services/brain_v3/gpu_serializer.py`
- Verify/possibly modify: `services/convert_service.py`
- Verify/possibly modify: `scripts/spike_brain_v3_nvenc_conflict.py`
- Verify/possibly modify: `tests/gui_harness.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-276-brain-v3-nvenc-render-not-serialized.md`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-277-gui-harness-shutdown-force-fallback.md`

- [ ] **Step 1: Quote plan task**

```text
Phase 6 B-276: echter Renderpfad mit Brain-Inferenz live pruefen.
```

- [ ] **Step 2: Run existing B-276 tests**

Run:

```powershell
python -m pytest tests/test_services/test_brain_v3_gpu_serializer.py tests/test_services/test_brain_v3_nvenc_serialization.py tests/test_services/test_brain_v3_nvenc_conflict_script.py -q
```

Expected:

```text
Tests pass before live render.
```

- [ ] **Step 3: Live render + Brain inference**

In app UI:

```text
Start Brain V3 inference path or embedding path.
Start real proxy/master render path using NVENC.
Observe logs for GpuSerializer holder "render".
Observe no overlapping Brain inference holder while render holds lock.
Observe no OOM.
```

Acceptance:

```text
B-276 may move only after real UI convert/proxy/master path was clicked and logs confirm serialization.
```

- [ ] **Step 4: Quote B-277**

```text
Phase 6 B-277: GUI-Harness Shutdown ohne Force-Fallback stabilisieren.
```

- [ ] **Step 5: Reproduce harness shutdown**

Run:

```powershell
python tests\gui_harness.py start --force
python tests\gui_harness.py wait-window --title PB_studio --timeout 45
python tests\gui_harness.py kill --grace-sec 25
```

Expected for B-277 fix:

```text
method is not "force".
App closeEvent shutdown log appears.
No python.exe / ollama.exe app leftovers.
```

- [ ] **Step 6: If force fallback persists**

Before code edit, identify exact cause:

```text
Does harness fail to send close?
Does app ignore close?
Does closeEvent hang?
Which shutdown stage is last log line?
```

Only then modify `tests/gui_harness.py` or app shutdown code.

---

## Task 7: Pending Studio-Brain GUI Verifications B-196 To B-199

**Files:**

- Verify: `main.py`
- Verify: `ui/studio_brain_window.py`
- Verify: `ui/widgets/graph_cockpit_tab.py`
- Verify: `services/graph/cockpit_view_model.py`
- Verify: `workers/memory_updater.py`
- Verify: `services/pacing_service.py`
- Update: B-196, B-197, B-198, B-199 vault files.

- [ ] **Step 1: Quote tasks**

```text
B-196 | code-fix-pending-gui-verification | Studio-Brain-Open haengt / AA_ShareOpenGLContexts
B-197 | code-fix-pending-gui-verification | Brain-Wiring-Quickfixes F-2/F-3/F-4
B-198 | code-fix-pending-gui-verification | SteerTab.runRequested -> AutoEdit
B-199 | code-fix-pending-gui-verification | Graph-Cockpit-Populator
```

- [ ] **Step 2: Run guard tests**

Run:

```powershell
python -m pytest tests/test_services/test_brain_wiring_b197.py tests/test_services/test_brain_wiring_b198_b199.py tests/test_ui/test_graph_cockpit_tab.py tests/ui/test_studio_brain_window.py -q
```

Expected:

```text
All guard tests pass. If not, stop.
```

- [ ] **Step 3: Live GUI**

In app:

```text
Open Studio Brain.
Confirm no hang.
Open Graph Cockpit.
Confirm graph populated with real data or explicit empty state if DB has no graph data.
Click refresh.
Click StoryMap thumbnail and verify timeline navigation.
Select audio in Steer tab.
Click Run.
Confirm auto_edit worker starts.
Record one verdict/rating and verify memory updater path logs.
```

Acceptance:

```text
Each bug can move only if its own real GUI path is confirmed.
```

---

## Task 8: Active Non-Brain Bugs With Code Scope

### Task 8.1: B-175 Soft-Delete Re-Import

**Files:**

- Likely modify: `database/models.py`
- Likely modify: import/ingest path found by searching `AudioTrack(` and `VideoClip(` insert call sites.
- Test: `tests/test_database/test_soft_delete_reimport_b175.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-175-soft-delete-unique-constraint-blocks-reimport.md`

- [ ] **Step 1: Quote bug**

```text
B-175 | open | Re-Import nach Soft-Delete blockiert mit IntegrityError
```

- [ ] **Step 2: Decision gate**

Need user decision before code:

```text
Option B quick-fix undelete-on-import, or Option A schema partial unique index migration.
```

Do not implement until decision exists.

### Task 8.2: B-219 WinError 32 Proxy Lock

**Files:**

- Verify/possibly modify: `services/video_service.py`
- Test: `tests/test_services/test_b219_winerror32_retry.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-219-winerror32-proxy-file-lock-after-pipeline.md`

- [ ] **Step 1: Quote bug**

```text
B-219 | open | WinError 32 Proxy-File-Lock zwischen Pipeline und BatchAnalysis
```

- [ ] **Step 2: Re-run existing tests**

Run:

```powershell
python -m pytest tests/test_services/test_b219_winerror32_retry.py -q
```

Expected:

```text
If tests already pass, status is inconsistent with vault. Need live pipeline -> batch analysis repro before new code.
```

- [ ] **Step 3: Live repro**

In app:

```text
Import 16 videos.
Run Video Pipeline.
Immediately run Video analysieren / BatchAnalysis on same clip set.
Watch first clip and proxy logs.
```

Acceptance:

```text
No WinError 32. If reproduced, fix exact failing path only.
```

### Task 8.3: B-270 EDL Export Dependency

**Files:**

- Verify/possibly modify: dependency manifest used by conda/pip install.
- Verify/possibly modify: `services/timeline_service.py` only if dependency detection/user error is wrong.
- Test: `tests/test_export_convert_real.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-270-edl-export-missing-opentimelineio-contrib.md`

- [ ] **Step 1: Quote bug**

```text
B-270 | open | EDL export missing opentimelineio-contrib
```

- [ ] **Step 2: Decision gate**

Need approval to add dependency:

```text
Install/add opentimelineio-contrib to project dependency set, or keep graceful error and document optional install.
```

Do not change dependencies without approval.

---

## Task 9: Design-Decision Bugs

### Task 9.1: B-229 Temporal Band Normalization

**Files:**

- Potential modify after decision: `services/spectral_analysis_service.py`
- Potential test: `tests/test_services/test_spectral_temporal_bands_b229.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-229-spectral-temporal-bands-per-window-normalization.md`

- [ ] **Step 1: Quote bug**

```text
B-229 | open | _compute_temporal_bands per-window normalization defeats timbral evolution
```

- [ ] **Step 2: Decision gate**

Ask user for one option:

```text
Option 1: track-global normalization.
Option 2: raw / unnormalized.
Option 3: expose both window-normalized and raw/global values.
```

No code before decision.

### Task 9.2: B-231 Analyze Extended Memory Peak

**Files:**

- Potential modify after decision: `services/spectral_analysis_service.py`
- Potential test: `tests/test_services/test_spectral_analyze_extended_b231.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-231-spectral-analyze-extended-double-stft-memory-peak.md`

- [ ] **Step 1: Quote bug**

```text
B-231 | open | analyze_extended laedt y und STFT doppelt
```

- [ ] **Step 2: Caller audit before code**

Run:

```powershell
Select-String -Path (Get-ChildItem -Recurse -File -Include *.py).FullName -Pattern 'analyze_extended'
```

Expected:

```text
All call sites listed before API changes.
```

- [ ] **Step 3: Decision gate**

Need user approval for refactor shape:

```text
Preferred: internal helper _analyze_with_audio_buffer() returning analysis result plus shared buffers; analyze() and analyze_extended() stay public-compatible.
```

No code before decision.

---

## Task 10: Phase-Level Synthesis And User Marker

**Files:**

- Create/update: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\phase-X-done-2026-05-07.md`
- Update: `C:\Brain-Bug\projects\pb-studio\log.md`
- Do not auto-set phase `fixed` / `DONE`.

- [ ] **Step 1: Summarize phase evidence**

For each phase 1 to 6, write:

```text
What was live-tested
What was only unit/service-tested
What failed
What remains open
Which bug files changed
Which commit hashes exist
```

- [ ] **Step 2: Ask user for marker**

Use exact rule:

```text
User muss Phase-Level-Marker setzen; Agent darf fixed/DONE nicht allein setzen.
```

- [ ] **Step 3: Commit discipline**

For code changes only:

```powershell
git add <exact files>
git commit -m "<type>(B-XXX): <short>" -m "<verification status>"
```

If no live verification:

```text
Commit body contains: (unverified - pending user test)
```

---

## Execution Order Summary

1. Task 0: Gate and working tree.
2. Task 0.5: SCHNITT Governance Gate B-310/B-316..B-320.
3. Task 1: B-265 CUDA preflight.
4. Task 2: Phase 1 live import/re-import.
5. Task 3: Phase 2 embedding/re-import.
6. Task 4: Phase 3/4 service/live path.
7. Task 5: Phase 5 UI, B-272 to B-275.
8. Task 6: Phase 6 B-276 and B-277.
9. Task 7: Older Studio-Brain GUI verifications B-196 to B-199.
10. Task 8: Active non-Brain code-scope bugs B-175, B-219, B-270.
11. Task 9: Design-decision bugs B-229, B-231.
12. Task 10: Phase-level synthesis and user marker.

## Open Decisions Before Execution

- B-310/B-316: User-Bestaetigung entscheidet, ob Teil-Live-Befund fuer Audio-Metadaten genuegt oder B-317 zuerst gefixt werden muss.
- B-175: undelete-on-import quick fix or schema partial unique index migration?
- B-229: temporal band normalization option?
- B-231: approve helper/refactor for shared audio/STFT buffers?
- B-270: add `opentimelineio-contrib` dependency or keep optional dependency error?
- Phase markers: user decides after evidence.

## Self-Review

- Spec coverage: all tasks from source synthesis mapped to Tasks 1-10.
- Placeholder scan: no `TBD`/`TODO` placeholders used as implementation steps.
- Type consistency: plan uses existing bug ids and file paths read from Vault/plan docs.
- Honesty: no `fixed`, `works`, or `DONE` claim made by this plan.
