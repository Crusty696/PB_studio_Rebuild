# Full Project Conflict Quality Audit - Top-Down Pass 2026-06-07

plan_id: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07
task: Task 2 Top-Down Audit
status: static-complete
mode: audit-plan
created: 2026-06-07

## Task Quote

```text
Audit governance, entrypoints, configuration, launch scripts, CI, runtime manifests, dependencies, data stores, workers, UI/API workflows, destructive operations, GPU/runtime constraints, and known bug status from system shape to implementation.
```

## Evidence Commands

```powershell
git status --short --branch
rg -n "PB-STUDIO-FULL-AUDIT-FIXPLAN|PB-STUDIO-CONFLICT-QUALITY-AUDIT|Current Active Plan|Current Branch|Default-Gate|next_allowed_task|active_plan_id" docs/superpowers/AGENT_HANDOFF.md docs/superpowers/ACTIVE_PLAN.md docs/superpowers/PLAN_REGISTRY.md docs/superpowers/plans/2026-06-07-full-project-conflict-quality-audit.md
rg -n "requirements\.txt|requirements-py310-cu113|environment\.yml|poetry|torch==|torch =|cu124|cu113|Python 3\.10|Python 3\.11" setup_pb_studio.py setup_pb_studio.bat start_pb_studio.py start_pb_studio.bat pyproject.toml requirements-py310-cu113.txt requirements.txt environment.yml poetry.lock README.md STARTUP.md .github/workflows/ci.yml
rg -n "shutil\.which\(" services workers ui agents scripts tools main.py start_pb_studio.py setup_pb_studio.py --glob "*.py"
rg -n "subprocess\.(run|Popen)" services workers ui agents scripts tools main.py start_pb_studio.py setup_pb_studio.py --glob "*.py"
rg -n "\"ffmpeg\"|\"ffprobe\"|get_ffmpeg_bin|get_ffprobe_bin" services workers ui agents scripts tools main.py start_pb_studio.py setup_pb_studio.py --glob "*.py"
rg -n "QThread\(|moveToThread|finished\.connect|deleteLater|QueuedConnection|processEvents\(|setStyleSheet\(|QTableWidget|QTableView" main.py ui services workers --glob "*.py"
rg -n "GPU_LOAD_LOCK|GPU_EXECUTION_LOCK|torch\.device\(|cuda:0|torch\.cuda|float16|bf16|bfloat16|ModelManager|ensure_loaded" services workers agents main.py tests --glob "*.py"
rg -n "^id:|^title:|^status:|^severity:|^plan_id:" C:\Brain-Bug\projects\pb-studio\wiki\bugs -g "B-45*.md" -g "B-46*.md" -g "B-47*.md"
```

## Architecture Map

Observed static architecture:

- Entry point: `main.py` creates `QApplication`, bootstraps DB, then creates `PBWindow` (`main.py:1323`, `main.py:1549`, `main.py:1624` from command evidence).
- Desktop model: single-process PySide6 app; no FastAPI/server entrypoint observed in top-down pass.
- UI root: `main.py:214` `PBWindow(QMainWindow)`.
- Task engine: `services/task_manager.py` provides `GlobalTaskManager`; QThread setup appears in `services/task_manager.py:275-366`.
- DB layer: `database/session.py` creates SQLAlchemy engine and exposes `nullpool_session`; soft-delete columns exist in `database/models.py:39`, `:85`, `:127`.
- AI/model layer: `services/model_manager.py` owns `GPU_LOAD_LOCK`, `GPU_EXECUTION_LOCK`, CUDA checks, unload, and model lifecycle.
- FFmpeg resolver: `services/startup_checks.py` defines `get_ffmpeg_bin()` / `get_ffprobe_bin()`.
- Agents: `agents/orchestrator_agent.py` routes to specialist agents and may call `ensure_loaded()` for agent model IDs.

## Dependency / Runtime Matrix

| Source | Observed fact | Audit interpretation |
|---|---|---|
| `requirements-py310-cu113.txt:1-10` | Active target is Python 3.10 + CUDA 11.3 / torch `1.12.1+cu113`. | Matches GTX 1060 rule. |
| `environment.yml:1-31` | Conda env uses Python 3.10 and pip installs `requirements-py310-cu113.txt`. | Active setup path consistent. |
| `.github/workflows/ci.yml:56-73` | CI unit tests use Python 3.10 and install `requirements-py310-cu113.txt`. | CI target matches active setup path. |
| `requirements.txt:1-4`, `:119-121` | File is documented legacy/future Python 3.11+cu124 and pins torch `2.5.1+cu124`. | Not active per docs; risk if any script/user installs it by mistake. |
| `poetry.lock:3098-3110` | Lock contains `torchaudio-2.4.1+cu118`, `torch = "2.4.1"`, source `pytorch-cu118`. | Drift candidate: Poetry lock does not reflect active cu113 runtime. Not proven active in launch path. |
| `pyproject.toml:8-13`, `:106-108` | Comments say active setup is `requirements-py310-cu113.txt` / `environment.yml`; Poetry source is cu113. | pyproject comments mitigate lock drift, but lock remains misleading artifact. |

## Findings

| ID | Severity | Category | Evidence | Observed fact | Impact | Verification |
|---|---|---|---|---|---|---|
| CQ-001 | high | governance conflict | `ACTIVE_PLAN.md:4-5`; `AGENT_HANDOFF.md:31`, `:39`, `:97-103` | Active plan is `PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07`, but handoff still says branch/active plan/default gate for `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31`. | Next agent can resume wrong plan or run obsolete default-gate task. | read-only static |
| CQ-002 | medium | worktree isolation | `git status --short --branch` output: branch `codex/PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` while active plan is new audit. | Current branch name no longer matches active task. | Cross-agent handoff and push review can confuse audit commits with old fixplan work. | command evidence |
| CQ-003 | medium | runtime drift | `poetry.lock:3098-3110`; `requirements-py310-cu113.txt:1-10`; `environment.yml:1-31` | Active runtime is cu113/torch 1.12.1, but `poetry.lock` contains cu118/torch 2.4.1 dependency graph. | If Poetry is used, it can create unsupported GPU/runtime stack for GTX 1060 rules. | read-only static |
| CQ-004 | high | FFmpeg resolver bypass | `workers/video.py:634-643`; `ui/widgets/media_grid.py:151-155`; central resolver evidence in `services/startup_checks.py:43-56` and many service imports. | Thumbnail extraction paths still call bare `"ffmpeg"` instead of `get_ffmpeg_bin()`. | Packaged/local FFmpeg may be bypassed; UI thumbnail generation can fail on machines where PATH lacks FFmpeg even though app resolver knows it. | read-only static |
| CQ-005 | medium | FFprobe resolver bypass | `services/ingest_service.py:124-127`, `:231-240`; central resolver evidence in `services/startup_checks.py:43-56`. | `ingest_service.py` uses env fallback `"ffprobe"`/`"ffmpeg"` instead of central resolver. | Import/probe behavior can diverge from startup checks and packaged binary path. | read-only static |
| CQ-006 | medium | known-bug status drift | `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-470-project-create-ui-freeze-blocking-idle-wait-on-main-thread.md:5` status `open-root-cause-needs-live-stack`; `C:\Brain-Bug\projects\pb-studio\log.md:247-249` Stack-A fix entry; `:239` default-gate/live starts; `:224` live-green entry. | B-470 vault status does not reflect documented Stack-A progress. | Fix planning can re-open already handled sub-scope or hide remaining sub-scope distinction. | vault/read-only static |
| CQ-007 | low | UI performance debt | `rg` count: 414 hits for `QTableWidget`/`QTableView`/`setStyleSheet`; `QTableWidget` instances in `ui/workspaces/media_workspace.py:361`, `ui/widgets/analysis_status_panel.py:185`, `ui/dialogs/model_manager_dialog.py:298/426/473/605`. | Many per-widget styles and table widgets remain. | Optimization candidate for large-data UI; not proven bug without profiling. | read-only static |

## Known Bug / Status Snapshot

| Bug | Vault status | Top-down note |
|---|---|---|
| B-458 | `code-fix-pending-live-verification` | Handoff also says live verification still open after refinement. |
| B-459 | `code-fix-pending-live-verification` | Not in current active plan; remains open live path. |
| B-460 | `code-fix-pending-live-verification` | Long LUFS rerun still pending live proof. |
| B-461 | `fixed` | Vault says fixed. No reclassification in this audit. |
| B-462 | `code-fix-pending-live-verification` | Handoff says fixed marker user-only. |
| B-463 | `code-fix-pending-live-verification` | Handoff says fixed marker user-only. |
| B-464..B-468 | `open` | Still open findings from prior live verify. |
| B-469 | `parked-not-reproducible-monitoring` | Status matches no reliable repro. |
| B-470 | `open-root-cause-needs-live-stack` | Drift candidate because log documents Stack-A live-green. |
| B-471 | `open` | Cluster still open; handoff says T4 live verify and T5 direction open. |

## Not Checked In Task 2

- No test collection run.
- No source call graph built beyond top-down `rg` evidence.
- No live UI path run.
- No runtime import/smoke test run.
- No dead-code confirmation; that belongs to Task 3 bottom-up.

## Verification Status

Static top-down pass complete. No app code changed. No live verification performed. No finding marked fixed.
