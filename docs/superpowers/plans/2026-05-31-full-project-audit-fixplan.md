# PB Studio Full Project Audit Fixplan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the full-project audit findings FPA-001..FPA-010 into a sequential, test-first fix and verification program.

**Architecture:** This plan treats the audit findings as gate failures until proven by tests or live runs. First make test/runtime gates honest, then fix narrow code surfaces with failing tests, then run live GPU/UI/Ollama paths only after unit and integration gates give evidence.

**Tech Stack:** Python 3.10 runtime, PySide6, pytest, GitHub Actions, SQLite/SQLAlchemy, FFmpeg/ffprobe, CUDA/torch on NVIDIA GTX 1060 6 GB, Ollama/local agent services.

---

plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
status: approved-for-planning
created: 2026-05-31
source_audit: PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31
source_report: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\full-project-file-audit-final-2026-05-31.md

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

No implementation task yet.

User must explicitly authorize implementation after reviewing this fixplan.
