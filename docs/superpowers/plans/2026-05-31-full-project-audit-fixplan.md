# PB Studio Full Project Audit Fixplan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the full-project audit findings FPA-001..FPA-010 into a sequential, test-first fix and verification program.

**Architecture:** This plan treats the audit findings as gate failures until proven by tests or live runs. First make test/runtime gates honest, then fix narrow code surfaces with failing tests, then run live GPU/UI/Ollama paths only after unit and integration gates give evidence.

**Tech Stack:** Python 3.10 runtime, PySide6, pytest, GitHub Actions, SQLite/SQLAlchemy, FFmpeg/ffprobe, CUDA/torch on NVIDIA GTX 1060 6 GB, Ollama/local agent services.

---

plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
status: in_progress
created: 2026-05-31
source_audit: PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31
source_report: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\full-project-file-audit-final-2026-05-31.md
implementation_authorized_by_user: 2026-05-31 chat

## Scope

Included findings:

- FPA-001 CI/default test gate does not prove runtime behavior.
- FPA-002 runtime environment drift between app, CI, and dependency manifests.
- FPA-003 boot path is highly coupled.
- FPA-004 project-switch/global DB state remains a live-concurrency risk.
- FPA-005 soft-delete/orphan invariants need default-test coverage and workflow proof.
- FPA-006 new video pipeline FFmpeg lookup can bypass packaged/local resolver.
- FPA-007 LLM/action boundary still needs live/default-gate coverage.
- FPA-008 QThread lifecycle has multiple valid-looking patterns, live behavior unproven.
- FPA-009 GPU/model serialization cannot be trusted from static locks alone.
- FPA-010 mutating/destructive surfaces need targeted tests before fixes.

Out of scope:

- UI redesign.
- Audio-V2 porting.
- ComfyUI integration.
- New features.
- Refactor-only cleanup without failing test or live failure.
- `status: fixed` without real app workflow evidence.

## Required Status Rules

- Each task starts with `git status --short --branch`.
- Each task reads its acceptance criteria before edits.
- Each code task writes/runs failing test before implementation.
- Each task writes Vault entry and commit.
- GUI/GPU/Ollama fixes stay `code-fix-pending-live-verification` unless real workflow runs with log/UI evidence.
- No bundled "fixed" marker at phase end.

## File Map

Likely modified files by task:

- `.github/workflows/ci.yml` - CI gate definition.
- `pyproject.toml` - pytest addopts/markers/test policy.
- `requirements-py310-cu113.txt` - only if implementation confirms dependency drift requires pin alignment.
- `environment.yml` - only if implementation confirms dependency drift requires pin alignment.
- `services/video_pipeline/primitives/decoder.py` - FFmpeg resolver alignment.
- `services/video_pipeline/primitives/proxy_generator.py` - FFmpeg resolver alignment.
- `services/video_pipeline/primitives/stream_hasher.py` - FFmpeg/ffprobe resolver alignment if confirmed.
- `tests/test_services/test_video_decoder_primitive.py` - resolver regression tests.
- `tests/test_services/test_video_proxy_generator.py` - resolver regression tests.
- `tests/test_services/test_video_stream_hasher.py` - resolver regression tests if source uses PATH-only lookup.
- `tests/test_services/test_db_project_switch_live_guard.py` - project-switch worker-idle/concurrency guard tests.
- `services/project_manager.py` and/or `database/session.py` - only if failing tests confirm unsafe switch path.
- `tests/test_services/test_soft_delete_visibility.py` - soft-delete/orphan visibility tests.
- `tests/test_agents/test_local_agent_action_boundary.py` - deterministic action boundary tests.
- `services/local_agent_service.py` and/or `services/action_registry.py` - only if failing tests confirm boundary issue.
- `tests/test_services/test_qthread_lifecycle_contract.py` - QThread lifecycle contract tests.
- `services/task_manager.py`, `ui/controllers/worker_dispatcher.py`, `workers/base.py` - only if failing tests confirm lifecycle issue.
- `tests/test_services/test_gpu_lock_contract.py` - static/unit GPU lock contract tests.
- `tests/test_services/test_mutating_surfaces_guards.py` - destructive/mutating guard tests.
- `docs/superpowers/synthesis/` and `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\` - verification reports.

## Task 0: Governance And Baseline

**Files:**
- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Modify: `docs/superpowers/PLAN_REGISTRY.md`
- Modify: `docs/superpowers/plans/2026-05-31-full-project-audit-fixplan.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-055-full-project-audit-fixplan.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-full-project-audit-fixplan-2026-05-31.md`

- [ ] **Step 1: Confirm clean start**

Run:

```powershell
git status --short --branch
powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1
```

Expected:

```text
No dirty worktree paths from another task.
```

- [ ] **Step 2: Confirm active plan**

Run:

```powershell
Get-Content docs\superpowers\ACTIVE_PLAN.md
Get-Content docs\superpowers\PLAN_REGISTRY.md
```

Expected:

```text
PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31 is active and next task is Task 1 after implementation authorization.
```

- [ ] **Step 3: Commit governance only**

Run:

```powershell
git add docs/superpowers/ACTIVE_PLAN.md docs/superpowers/PLAN_REGISTRY.md docs/superpowers/plans/2026-05-31-full-project-audit-fixplan.md
git commit -m "docs(PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31): authorize fixplan" -m "Verification: governance documentation only; no code changes; no tests run; no app live verification."
```

Expected:

```text
Commit created. No product code changed.
```

## Task 1: Honest Test Gate Policy

**Findings:** FPA-001, FPA-002

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Create: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Write failing policy check**

Create a pytest or script check that fails while CI has no pytest command and `pyproject.toml` hides deep/live suites without documented manual commands.

Run:

```powershell
rg -n "pytest|ruff|bandit" .github\workflows\ci.yml
rg -n "addopts|markers|testpaths" pyproject.toml
```

Expected now:

```text
CI has no pytest gate. addopts ignores deep/live files.
```

- [ ] **Step 2: Add CI unit gate**

Minimum acceptable CI command:

```yaml
- name: Run unit tests
  run: pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings
```

If PySide6/Windows-only failures block Linux CI, mark exact skipped groups and document them in `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`.

- [ ] **Step 3: Make ignored suites explicit**

`pyproject.toml` must keep markers but document manual commands:

```toml
markers = [
    "gui: marks tests that require a display (deselect with -m 'not gui')",
    "e2e: marks end-to-end tests (deselect with -m 'not e2e')",
    "slow: marks slow tests (deselect with -m 'not slow')",
    "integration: marks integration tests",
    "live_gpu: marks tests that load real GPU models (skip with -m 'not live_gpu')",
]
```

Manual commands to document:

```powershell
pytest tests/test_db_deep.py -v
pytest tests/live_ollama_integration_test.py -v
pytest tests/test_services/test_video_pipeline_e2e_live.py -m live_gpu -v
```

- [ ] **Step 4: Run gate**

Run:

```powershell
pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings
```

Expected:

```text
PASS, or first real failing test documented as blocker with exact failure.
```

- [ ] **Step 5: Vault + commit**

Write synthesis with command output summary. Commit:

```powershell
git add .github/workflows/ci.yml pyproject.toml docs/superpowers/synthesis/test-gate-policy-2026-05-31.md
git commit -m "test(FPA-001): add honest default test gate" -m "Verification: default pytest gate run; status documented in synthesis."
```

## Task 1a: B-441 Structure Enrichment Default-Gate Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-441-default-gate-structure-enrichment-zero-scenes.md`

**Files:**
- Test: `tests/integration/test_full_enrichment.py`
- Modify only if root cause proves it: `workers/structure_enrichment.py`
- Modify only if root cause proves it: enrichment/vector DB fixture setup used by `tests/integration/test_full_enrichment.py`
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/integration/test_full_enrichment.py::test_full_enrichment_on_tiny_synthetic_library -v -s
```

Expected:

```text
Failure reproduces with Expected 54 enriched scenes, got 0, or current behavior is documented exactly.
```

- [ ] **Step 2: Trace data source**

Read `tests/integration/test_full_enrichment.py` and `workers/structure_enrichment.py`. Identify where synthetic scene embeddings are inserted and where `StructureEnrichmentWorker` queries them.

Expected:

```text
Root cause documented: mismatch between fixture population and worker query, missing vector DB population, or changed schema/query contract.
```

- [ ] **Step 3: Add minimal failing regression assertion**

If the existing integration failure is broad, add a smaller assertion in `tests/integration/test_full_enrichment.py` that proves the populated fixture is visible to the worker's query path before enrichment.

Expected:

```text
Test fails before implementation for the same root cause.
```

- [ ] **Step 4: Implement one root-cause fix**

Allowed fixes:

```text
Fixture writes embeddings into the storage path/session the worker actually reads.
```

or

```text
Worker reads the existing fixture-populated embedding source through the intended contract.
```

Do not skip the integration test. Do not relax the expected scene count unless root-cause evidence proves expected data changed intentionally.

- [ ] **Step 5: Verify targeted and default gate**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/integration/test_full_enrichment.py::test_full_enrichment_on_tiny_synthetic_library -v
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings
```

Expected:

```text
Targeted test passes. Default gate passes or next first failure is documented as a new blocker/bug.
```

- [ ] **Step 6: Vault + commit**

Update B-441 and synthesis. Commit:

```powershell
git add tests/integration/test_full_enrichment.py workers/structure_enrichment.py docs/superpowers/synthesis/test-gate-policy-2026-05-31.md docs/superpowers/ACTIVE_PLAN.md docs/superpowers/PLAN_REGISTRY.md docs/superpowers/plans/2026-05-31-full-project-audit-fixplan.md
git commit -m "fix(B-441): restore structure enrichment default gate" -m "Verification: targeted enrichment test run; default gate status documented."
```

## Task 1b: B-443 Pacing Cut Point Default-Gate Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-443-default-gate-pacing-cut-points-source-not-beat.md`

**Files:**
- Test: `tests/test_new_features.py`
- Modify only if root cause proves it: `services/pacing_service.py`
- Modify only if root cause proves it: `services/pacing_beat_grid.py`
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_new_features.py::TestPacingService::test_calculate_cut_points_with_bpm -v
```

- [ ] **Step 2: Trace source selection**

Read `tests/test_new_features.py`, `services/pacing_service.py`, and `services/pacing_beat_grid.py`. Identify why cuts from a BPM-backed track are not all `source == "beat"`.

- [ ] **Step 3: Implement root-cause fix only**

Do not change the assertion unless evidence proves the test contract is obsolete.

- [ ] **Step 4: Verify targeted and default gate**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_new_features.py::TestPacingService::test_calculate_cut_points_with_bpm -v
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings --cache-clear -q
```

## Task 1c: B-444 Grid Stability Default-Gate Crash Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-444-default-gate-grid-stability-access-violation.md`

**Files:**
- Test: `tests/test_grid_stability.py`
- Modify only if root cause proves it: `ui/widgets/media_grid.py`
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact crash**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_grid_stability.py::test_grid_with_invalid_paths -vv --tb=short
```

If targeted test passes, reproduce the order-dependent crash from the default gate and capture the last completed test plus exit code.

- [ ] **Step 2: Trace Qt/media-grid teardown**

Read `tests/test_grid_stability.py` and `ui/widgets/media_grid.py`. Identify whether crash is caused by QApplication reuse, pending thumbnail work, widget deletion, invalid image/path handling, or previous-suite state.

- [ ] **Step 3: Implement root-cause fix only**

Do not skip the test unless evidence proves it is inherently live/GUI-only and must be moved behind a marker.

- [ ] **Step 4: Verify targeted and default gate**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_grid_stability.py::test_grid_with_invalid_paths -vv --tb=short
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings --cache-clear -q
```

Expected:

```text
Targeted test passes. Default gate passes or next first failure/crash is documented as a new blocker/bug.
```

## Task 1d: B-445 Pacing Scoring Performance Default-Gate Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-445-default-gate-pacing-scoring-latency-regression.md`

**Files:**
- Test: `tests/integration/test_pacing_performance.py`
- Modify only if root cause proves it: pacing scorer / weights-loader hot path modules.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact performance failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/integration/test_pacing_performance.py::test_scoring_latency_per_cut_under_budget -vv --tb=short
```

- [ ] **Step 2: Trace scorer hot path**

Read `tests/integration/test_pacing_performance.py` and the scorer modules used by the test. Identify whether overhead comes from formula evaluation, weights loading, object allocation, or test environment variance.

- [ ] **Step 3: Implement root-cause fix only**

Do not loosen the threshold unless evidence proves the budget is obsolete.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted performance test and default gate. Document next first failure if default gate still fails.

## Task 1e: B-446 Pre-Cache Headless Default-Gate Crash Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-446-default-gate-pre-cache-headless-crash.md`

**Files:**
- Test: `tests/test_pre_cache_headless.py`
- Modify only if root cause proves it: pre-cache / model-cache / Qt-headless startup modules used by the test.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact crash**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_pre_cache_headless.py::test_pre_cache_headless_mode -vv --tb=short
```

- [ ] **Step 2: Trace headless pre-cache path**

Read `tests/test_pre_cache_headless.py` and the invoked pre-cache code. Identify why it crashes under default-gate order.

- [ ] **Step 3: Implement root-cause fix only**

Do not skip the test unless evidence proves it is inherently live/GPU-only and must be moved behind a marker.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted pre-cache test and default gate. Document next first failure if default gate still fails.

## Task 1f: B-447 Power Status Change Regression Test Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-447-default-gate-b433-power-status-regression.md`

**Files:**
- Test: `tests/test_services/test_b433_power_status_change_cuda_reprobe.py`
- Modify only if root cause proves it: `main.py` power-event filter code.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_b433_power_status_change_cuda_reprobe.py -vv --tb=short
```

- [ ] **Step 2: Trace B-433 power-status branch**

Read the test and the `main.py` power-event filter. Identify whether the source-inspection test is stale or the `0x000A` branch lost the `ModelManager.notify_power_resume()` call.

- [ ] **Step 3: Implement root-cause fix only**

Do not loosen the test unless evidence proves the app code still handles the branch correctly through another explicit path.

- [ ] **Step 4: Verify targeted and default gate**

Run the targeted B-433 test and default gate. Document next first failure if default gate still fails.

## Task 1g: B-448 Brain V3 Performance Profile Default-Gate Failure Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-448-default-gate-brain-v3-performance-profile-learning-timeout.md`

**Files:**
- Test: `tests/test_services/test_brain_v3_performance_profile_script.py`
- Modify only if root cause proves it: `scripts/spike_brain_v3_performance_profile.py` and modules used by the isolated pacing smoke script.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_brain_v3_performance_profile_script.py::test_performance_profile_collects_pacing_samples -vv --tb=short
```

- [ ] **Step 2: Trace performance profile script**

Read the test, `scripts/spike_brain_v3_performance_profile.py`, and the isolated script it runs. Identify why `learning_session_under_2s` is false.

- [ ] **Step 3: Implement root-cause fix only**

Do not loosen the 2s threshold unless evidence proves the budget is obsolete or the test measures unrelated process/setup overhead.

- [ ] **Step 4: Verify targeted and default gate**

Run the targeted performance-profile test and default gate. Document next first failure if default gate still fails.

## Task 1h: B-449 Grid Stability Default-Gate Crash Recurrence Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-449-default-gate-grid-stability-crash-recurrence.md`

**Files:**
- Test: `tests/test_grid_stability.py`
- Modify only if root cause proves it: `ui/widgets/media_grid.py` and thumbnail-thread lifecycle code used by the test.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact crash**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -X faulthandler -m pytest tests/test_grid_stability.py -vv --tb=short
```

- [ ] **Step 2: Trace full-order grid lifecycle**

Read `tests/test_grid_stability.py`, `ui/widgets/media_grid.py`, and the default-gate log. Identify why the full default-gate order can still crash at `test_grid_delete_later_stops_thumbnail_threads` after B-444 targeted tests passed.

- [ ] **Step 3: Implement root-cause fix only**

Do not skip or mark the test as live-only unless evidence proves a Qt/native dependency cannot be isolated in pytest.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted grid tests and default gate. Document next first failure if default gate still fails.

## Task 1i: B-450 Brain Wiring B197 Default-Gate Failure Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-450-default-gate-brain-wiring-b197-pbwindow-mock.md`

**Files:**
- Test: `tests/test_services/test_brain_wiring_b197.py`
- Modify only if root cause proves it: `main.py` Brain/PBWindow wiring code or the test harness imports/mocks.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_brain_wiring_b197.py::test_main_pbwindow_has_brain_timeline_nav_slot -vv --tb=short
```

- [ ] **Step 2: Trace PBWindow import and mocks**

Read the test and the `main.py` PBWindow definition/import path. Identify why the test sees `PBWindow` as `MagicMock spec='str'`.

- [ ] **Step 3: Implement root-cause fix only**

Do not assert against mocks unless evidence proves the app wiring is already covered by a real import or source-level invariant.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted B-197 wiring test and default gate. Document next first failure if default gate still fails.

## Task 1j: B-451 Stem Separator CPU FP16 Clamp Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-451-default-gate-stem-separator-fp16-cpu-clamp.md`

**Files:**
- Test: `tests/test_services/test_stem_separator_audio_decode.py`
- Modify only if root cause proves it: `services/ai_audio_service.py` streaming stem writer dtype handling.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_stem_separator_audio_decode.py::test_streaming_stem_writer_crossfades_without_full_accumulator -vv --tb=short
```

- [ ] **Step 2: Trace dtype path**

Read the test and `services/ai_audio_service.py` streaming stem writer. Identify why CPU half tensors reach `Tensor.clamp(min=...)`.

- [ ] **Step 3: Implement root-cause fix only**

Do not force CUDA or install another GPU backend. GTX 1060 rule applies: CUDA only if available, otherwise CPU-safe dtype.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted stem separator test and default gate. Document next first failure if default gate still fails.

## Task 1k: B-452 Corrupt Video Pipeline Default-Gate Failure Follow-Up

**Findings:** FPA-001

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-452-default-gate-corrupt-video-pipeline-missing-clip-message.md`

**Files:**
- Test: `tests/test_workers/test_video_corrupt_clip.py`
- Modify only if root cause proves it: `workers/video.py`, `services/video_analysis_service.py`, video pipeline error mapping.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact failure**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_workers/test_video_corrupt_clip.py::test_corrupt_mp4_through_pipeline_does_not_crash -vv --tb=short
```

- [ ] **Step 2: Trace worker error path**

Read the test, captured logs, and worker/pipeline code. Identify why the test sees `VideoClip 99 nicht gefunden oder geloescht` instead of a corrupt/unreadable file message.

- [ ] **Step 3: Implement root-cause fix only**

Do not loosen the assertion unless evidence proves the worker cannot distinguish missing DB row from corrupt source in this path.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted corrupt-video test and default gate. Document next first failure if default gate still fails.

## Task 1l: B-453 Grid Stability Native Crash After B-452 Follow-Up

**Findings:** FPA-001, FPA-008

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-453-default-gate-grid-stability-native-crash-after-b452.md`

**Files:**
- Test: `tests/test_grid_stability.py`
- Modify only if root cause proves it: `ui/media_pool.py`, thumbnail worker cleanup, Qt signal/lifecycle code.
- Modify: `docs/superpowers/synthesis/test-gate-policy-2026-05-31.md`

- [ ] **Step 1: Reproduce exact crash**

Run the targeted grid stability test and a default-gate command with compact logging. If targeted stays green, identify the shortest order-dependent reproduction before editing.

- [ ] **Step 2: Trace Qt lifetime path**

Read `tests/test_grid_stability.py` and thumbnail worker cleanup paths. Identify why default order can still native-crash while targeted test passes.

- [ ] **Step 3: Implement root-cause fix only**

Do not mask the crash by skipping the test or weakening lifecycle assertions.

- [ ] **Step 4: Verify targeted and default gate**

Run targeted grid test(s) and default gate. Document next first failure if default gate still fails.

## Task 2: Runtime Manifest Drift Audit/Fix

**Findings:** FPA-002

**Files:**
- Modify only if needed: `requirements-py310-cu113.txt`
- Modify only if needed: `environment.yml`
- Modify only if needed: `pyproject.toml`
- Create: `docs/superpowers/synthesis/runtime-manifest-drift-2026-05-31.md`

- [ ] **Step 1: Produce drift table**

Run:

```powershell
python --version
python -m pip --version
python -m pip freeze
Get-Content requirements-py310-cu113.txt
Get-Content environment.yml
Get-Content pyproject.toml
```

Expected:

```text
Exact current interpreter, installed package set, and manifest pins captured.
```

- [ ] **Step 2: Decide by evidence**

If runtime uses `.venv310`, plan pins must align to Python 3.10/CUDA 11.3. If CI remains Python 3.11, document it as lint-only or add matrix with Python 3.10.

- [ ] **Step 3: Run import smoke**

Run:

```powershell
python -c "import torch, PySide6, sqlalchemy; print('imports-ok'); print(torch.__version__); print(torch.cuda.is_available())"
```

Expected:

```text
imports-ok plus exact torch/CUDA state, or blocker with exact ImportError.
```

- [ ] **Step 4: Commit only if changed**

Commit:

```powershell
git add requirements-py310-cu113.txt environment.yml pyproject.toml docs/superpowers/synthesis/runtime-manifest-drift-2026-05-31.md
git commit -m "chore(FPA-002): document runtime manifest drift" -m "Verification: import smoke run; runtime manifest evidence captured."
```

## Task 3: FFmpeg Resolver Unification

**Findings:** FPA-006

**Files:**
- Modify: `services/video_pipeline/primitives/decoder.py`
- Modify: `services/video_pipeline/primitives/proxy_generator.py`
- Modify: `services/video_pipeline/primitives/stream_hasher.py` if PATH-only lookup confirmed.
- Test: `tests/test_services/test_video_decoder_primitive.py`
- Test: `tests/test_services/test_video_proxy_generator.py`
- Test: `tests/test_services/test_video_stream_hasher.py` if source changed.

- [ ] **Step 1: Write failing resolver tests**

Tests must monkeypatch `services.startup_checks.get_ffmpeg_bin` and `get_ffprobe_bin`, then assert primitives use configured binaries instead of raw `shutil.which`.

Expected failure before fix:

```text
Assertion proves primitive ignored configured resolver.
```

- [ ] **Step 2: Implement minimal resolver use**

Replace PATH-only lookup with shared helper calls:

```python
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin

ffmpeg = str(get_ffmpeg_bin())
ffprobe = str(get_ffprobe_bin())
```

Do not change codec policy or pipeline behavior.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
pytest tests/test_services/test_video_decoder_primitive.py tests/test_services/test_video_proxy_generator.py tests/test_services/test_video_stream_hasher.py -v
```

Expected:

```text
PASS, or exact first failing test documented.
```

- [ ] **Step 4: Commit**

```powershell
git add services/video_pipeline/primitives tests/test_services
git commit -m "fix(FPA-006): use configured ffmpeg resolver in video primitives" -m "Verification: targeted video primitive tests run."
```

## Task 4: DB Project Switch And Soft-Delete Safety

**Findings:** FPA-004, FPA-005

**Files:**
- Test: `tests/test_services/test_db_project_switch_live_guard.py`
- Test: `tests/test_services/test_soft_delete_visibility.py`
- Modify only if failing tests require: `database/session.py`
- Modify only if failing tests require: `services/project_manager.py`
- Modify only if failing tests require: affected UI/service query file.

- [ ] **Step 1: Write project-switch guard test**

Test must simulate active worker/session state and assert project switch refuses or waits before swapping engine.

Expected failure:

```text
Switch happens while guard says worker/session active, or no guard exists.
```

- [ ] **Step 2: Write soft-delete visibility test**

Test must create project, audio/video, child rows, soft-delete parent, then assert workflow query excludes hidden media and does not expose orphaned child data.

Expected failure:

```text
Any active workflow query returns soft-deleted parent or orphan child.
```

- [ ] **Step 3: Implement minimal guard/filter fix**

Allowed fix patterns:

```python
if worker_registry.has_running_tasks():
    raise RuntimeError("Project switch blocked while tasks are running")
```

or explicit query filter:

```python
.filter(AudioTrack.deleted_at.is_(None))
```

No schema rewrite unless failing test proves schema change unavoidable.

- [ ] **Step 4: Run targeted DB tests**

Run:

```powershell
pytest tests/test_services/test_db_project_switch_live_guard.py tests/test_services/test_soft_delete_visibility.py tests/test_services/test_ingest_service.py -v
pytest tests/test_db_deep.py -v
```

Expected:

```text
PASS, or exact failing test documented. Deep DB suite result captured even if still manual.
```

- [ ] **Step 5: Commit**

```powershell
git add database services ui tests/test_services/test_db_project_switch_live_guard.py tests/test_services/test_soft_delete_visibility.py
git commit -m "fix(FPA-004): guard project switch during active work" -m "Verification: DB project-switch and soft-delete tests run; live app switch pending if GUI not run."
```

## Task 5: QThread Lifecycle Contract

**Findings:** FPA-008

**Files:**
- Test: `tests/test_services/test_qthread_lifecycle_contract.py`
- Modify only if failing tests require: `services/task_manager.py`
- Modify only if failing tests require: `ui/controllers/worker_dispatcher.py`
- Modify only if failing tests require: `workers/base.py`

- [ ] **Step 1: Write lifecycle contract tests**

Test cases:

```text
worker emits finished -> thread quits -> worker deleteLater scheduled.
worker emits error without finished -> thread quits -> cleanup runs.
cancel_task on running worker -> worker.cancel called -> thread quits or task marked cancelled.
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_services/test_qthread_lifecycle_contract.py tests/ui/test_worker_dispatcher_error_cleanup.py tests/test_services/test_task_manager.py -v
```

Expected:

```text
New contract failure identifies exact lifecycle gap, or all pass and finding becomes verified-by-unit.
```

- [ ] **Step 3: Implement only failing lifecycle fix**

Allowed minimal pattern:

```python
worker.error.connect(thread.quit)
worker.finished.connect(thread.quit)
thread.finished.connect(worker.deleteLater)
thread.finished.connect(thread.deleteLater)
```

No consolidation refactor unless tests prove duplicate behavior breaks.

- [ ] **Step 4: Commit**

```powershell
git add services/task_manager.py ui/controllers/worker_dispatcher.py workers/base.py tests/test_services/test_qthread_lifecycle_contract.py
git commit -m "fix(FPA-008): enforce qthread lifecycle contract" -m "Verification: lifecycle contract tests run; GUI live verification pending if no app run."
```

## Task 6: Deterministic LLM/Action Boundary Gate

**Findings:** FPA-007

**Files:**
- Test: `tests/test_agents/test_local_agent_action_boundary.py`
- Modify only if failing tests require: `services/local_agent_service.py`
- Modify only if failing tests require: `services/action_registry.py`

- [ ] **Step 1: Write deterministic boundary tests**

Tests must not require Ollama. Mock parsed model output and assert:

```text
destructive action with unknown params rejected before handler call.
destructive action without confirmation rejected before handler call.
safe action with exact params executes once.
malformed action JSON returns structured error, no side effect.
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
pytest tests/test_agents/test_local_agent_action_boundary.py tests/test_agents/test_action_registry.py -v
```

Expected:

```text
PASS, or exact failing test documented.
```

- [ ] **Step 3: Implement minimal boundary fix**

Allowed fix pattern:

```python
if action_name in DESTRUCTIVE_ACTIONS and not params.get("confirm"):
    return {"status": "error", "message": "Confirmation required"}
```

Handler must not be called before validation.

- [ ] **Step 4: Commit**

```powershell
git add services/local_agent_service.py services/action_registry.py tests/test_agents/test_local_agent_action_boundary.py
git commit -m "fix(FPA-007): gate local-agent action boundary" -m "Verification: deterministic action-boundary tests run; live Ollama pending."
```

## Task 7: Mutating Surface Guard Tests

**Findings:** FPA-010

**Files:**
- Test: `tests/test_services/test_mutating_surfaces_guards.py`
- Modify only if failing tests require: `start_pb_studio.py`
- Modify only if failing tests require: `services/project_manager.py`
- Modify only if failing tests require: `services/backup_service.py`
- Modify only if failing tests require: `services/vector_db_service.py`
- Modify only if failing tests require: `services/timeline_snapshot_service.py`

- [ ] **Step 1: Write guard tests**

Each test must assert target path stays inside project root or operation requires explicit confirmation.

Required cases:

```text
cache cleanup refuses path outside repo/app cache.
failed project save cleanup refuses parent/root path.
vector delete scopes to active project.
timeline snapshot clear scopes to active project.
```

- [ ] **Step 2: Run tests**

Run:

```powershell
pytest tests/test_services/test_mutating_surfaces_guards.py -v
```

Expected:

```text
PASS, or exact unsafe mutating path documented.
```

- [ ] **Step 3: Implement minimal guard**

Allowed helper:

```python
def _assert_inside(base: Path, target: Path) -> None:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if base_resolved != target_resolved and base_resolved not in target_resolved.parents:
        raise ValueError(f"Refusing path outside base: {target_resolved}")
```

- [ ] **Step 4: Commit**

```powershell
git add start_pb_studio.py services tests/test_services/test_mutating_surfaces_guards.py
git commit -m "fix(FPA-010): guard mutating surfaces" -m "Verification: mutating surface guard tests run."
```

## Task 8: GPU Serialization Verification Gate

**Findings:** FPA-009

**Files:**
- Test: `tests/test_services/test_gpu_lock_contract.py`
- Create: `docs/superpowers/synthesis/gpu-serialization-live-2026-05-31.md`
- Modify only if failing tests require: `services/model_manager.py`
- Modify only if failing tests require: `services/brain_v3/gpu_serializer.py`
- Modify only if failing tests require: `services/video_pipeline/stages/siglip_embed_stage.py`
- Modify only if failing tests require: `services/video_pipeline/stages/raft_motion_stage.py`

- [ ] **Step 1: Write unit lock contract tests**

Tests must assert shared lock objects or explicit serialization path is used by ModelManager, Brain V3 serializer, SigLIP stage, and RAFT stage.

- [ ] **Step 2: Run unit tests**

Run:

```powershell
pytest tests/test_services/test_gpu_lock_contract.py tests/test_services/test_video_model_services.py -v
```

Expected:

```text
PASS, or exact serialization gap documented.
```

- [ ] **Step 3: Run live GPU command only after unit pass**

Run on GTX 1060 machine:

```powershell
pytest tests/test_services/test_video_pipeline_e2e_live.py -m live_gpu -v
```

Expected:

```text
PASS with CUDA available, or exact failure/VRAM/OOM captured.
```

- [ ] **Step 4: Commit**

```powershell
git add services tests/test_services/test_gpu_lock_contract.py docs/superpowers/synthesis/gpu-serialization-live-2026-05-31.md
git commit -m "test(FPA-009): verify gpu serialization contract" -m "Verification: GPU unit gate run; live_gpu status documented."
```

## Task 9: Boot Path Guardrails

**Findings:** FPA-003

**Files:**
- Test: `tests/test_services/test_boot_startup_contract.py`
- Modify only if failing tests require: `main.py`
- Modify only if failing tests require: `services/startup_checks.py`
- Create: `docs/superpowers/synthesis/boot-live-2026-05-31.md`

- [ ] **Step 1: Write boot contract tests**

Tests assert:

```text
startup checks can run without creating QApplication.
DB init failure logs clear error and exits cleanly.
CUDA unavailable path logs degraded mode, not crash.
```

- [ ] **Step 2: Run boot contract tests**

Run:

```powershell
pytest tests/test_services/test_boot_startup_contract.py tests/test_services/test_startup_checks_gpu.py tests/test_services/test_startup_checks_environment.py -v
```

Expected:

```text
PASS, or exact boot contract failure documented.
```

- [ ] **Step 3: Run app live boot**

Run:

```powershell
python main.py
```

Manual/live expected:

```text
App window opens. Startup checks complete. Log contains no uncaught traceback.
```

If autonomous click path is impossible, status remains `code-fix-pending-live-verification`.

- [ ] **Step 4: Commit**

```powershell
git add main.py services/startup_checks.py tests/test_services/test_boot_startup_contract.py docs/superpowers/synthesis/boot-live-2026-05-31.md
git commit -m "test(FPA-003): add boot startup contract gate" -m "Verification: boot contract tests run; app live status documented."
```

## Task 10: Final Verification Matrix And Handoff

**Files:**
- Create: `docs/superpowers/synthesis/full-audit-fixplan-verification-2026-05-31.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\full-audit-fixplan-verification-2026-05-31.md`
- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Modify: `docs/superpowers/PLAN_REGISTRY.md`

- [ ] **Step 1: Build matrix**

Matrix rows:

```text
FPA-001 default test gate
FPA-002 runtime drift
FPA-003 boot path
FPA-004 project switch
FPA-005 soft-delete/orphan
FPA-006 FFmpeg resolver
FPA-007 LLM/action boundary
FPA-008 QThread lifecycle
FPA-009 GPU serialization
FPA-010 mutating surfaces
```

Columns:

```text
unit test, integration test, live test, vault file, commit hash, status
```

- [ ] **Step 2: Run handoff**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File tools\agent_handoff.ps1
```

Expected:

```text
OK: clean handoff state.
```

- [ ] **Step 3: Commit**

```powershell
git add docs/superpowers/ACTIVE_PLAN.md docs/superpowers/PLAN_REGISTRY.md docs/superpowers/synthesis/full-audit-fixplan-verification-2026-05-31.md
git commit -m "docs(PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31): record verification matrix" -m "Verification: handoff clean; matrix records exact test/live status."
```

## Implementation Stop Conditions

Stop and ask user if:

- Any task wants to change scope outside FPA-001..FPA-010.
- A failing test indicates architecture rewrite rather than local fix.
- GPU live run needs model/download/install not already present.
- CI fix requires changing supported Python/CUDA runtime.
- Worktree becomes dirty with unknown paths.
- Live GUI verification is required for `fixed` status.

## Current Next Task

Task 1l - B-453 Grid Stability Native Crash After B-452 Follow-Up.
