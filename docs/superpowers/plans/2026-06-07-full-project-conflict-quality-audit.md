# PB Studio Conflict Quality Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a new read-only whole-project audit for conflicts, bugs, gaps, false assumptions, inactive features, blockers, dead code, and stability/performance/quality improvements.

**Architecture:** Audit-plan mode only. The audit starts with inventory and exclusions, then uses one top-down pass and one independent bottom-up pass, then challenges findings before producing a fix-plan candidate. Findings require evidence; this plan authorizes no app-code edits, refactors, dependency swaps, or `fixed` status changes.

**Tech Stack:** Python 3.10 runtime, PySide6, pytest, SQLite/SQLAlchemy, FFmpeg/ffprobe, CUDA/torch on NVIDIA GTX 1060 6 GB, Ollama/local agent services, repo governance docs, Obsidian vault.

---

plan_id: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07
status: approved-for-planning
mode: audit-plan
created: 2026-06-07
authorized_by_user: 2026-06-07 chat

## Scope

Audit root:

```text
C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild
```

Included by default:

- tracked source files
- tracked tests and fixtures
- tracked scripts, launchers, wrappers, and CI files
- tracked docs and governance files
- tracked configuration files
- small untracked files after explicit inventory review
- vault notes needed for plan state, bug state, decisions, handoff, and live-verification claims

Targeted review areas:

- conflicts between `AGENTS.md`, `ACTIVE_PLAN.md`, `PLAN_REGISTRY.md`, repo plans, vault mirrors, decisions, and handoff files
- known bug files and stale status markers
- dead or unreachable code paths
- UI features that exist in code but are not wired into live workflows
- tests that assert outdated or fake behavior
- runtime/dependency drift, especially Python/torch/CUDA/FFmpeg/Ollama
- startup, project-switch, worker, QThread, GPU-lock, model-load, destructive-action, and cleanup paths
- performance risks on GTX 1060 6 GB and PySide6 UI thread
- data integrity risks around SQLite, soft-delete, orphaned rows, timelines, vectors, and generated artifacts

Excluded from manual every-file reading unless targeted evidence requires inspection:

- `.git/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- virtual environments and local package caches
- generated build output, installers, dist artifacts
- binary media, model weights, databases, logs, screenshots, and large archives
- third-party vendored dependency trees

## Evidence Standard

Every finding must include:

- exact file path and line when available
- command, file read, vault note, test name, or log evidence
- observed fact
- impact
- confidence level based on evidence
- verification status: read-only, static check, unit test, integration test, live verified, or not verified

No finding may be marked fixed. Audit report may propose fix tasks only.

## Required Status Rules

- Start every task with `git status --short --branch`.
- Stop if unknown dirty paths appear.
- Use `powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1` at session start and `tools\agent_handoff.ps1` before ending.
- Refresh vault index before vault-state answers when the vault tool is available.
- Do not run destructive or mutating commands.
- Do not edit app code.
- Do not mark bug or phase status `fixed`.
- Distinguish static evidence, unit evidence, integration evidence, and live evidence.

## File Map

Governance files:

- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Modify: `docs/superpowers/PLAN_REGISTRY.md`
- Create: `docs/superpowers/plans/2026-06-07-full-project-conflict-quality-audit.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-057-full-project-conflict-quality-audit.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-full-project-conflict-quality-audit-2026-06-07.md`

Audit output files:

- Create: `docs/superpowers/synthesis/full-project-conflict-quality-audit-inventory-2026-06-07.md`
- Create: `docs/superpowers/synthesis/full-project-conflict-quality-audit-final-2026-06-07.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\full-project-conflict-quality-audit-final-2026-06-07.md`

## Tasks

### Task 0: Governance Activation

Quote:

```text
Register and activate the audit plan in repo governance and vault.
```

Acceptance criteria:

- `git status --short --branch` is clean or only current governance files are dirty.
- plan exists in `docs/superpowers/plans/`.
- registry row exists.
- `ACTIVE_PLAN.md` selects exactly this plan.
- vault decision exists.
- vault plan mirror exists.

### Task 1: Inventory And Exclusion Map

Quote:

```text
Build complete repository file inventory, classify every file as included, excluded, or targeted-only, and write coverage evidence before deeper review.
```

Acceptance criteria:

- tracked files are enumerated by `git ls-files`.
- untracked files are enumerated separately.
- generated/cache/binary/vendor/build exclusions are documented with command evidence.
- final inventory report proves which file classes are included, excluded, or targeted-only.
- no app-code edits occur.

Commands:

```powershell
git status --short --branch
git ls-files
git status --short --untracked-files=all
git ls-files | Measure-Object
```

Output:

```text
docs/superpowers/synthesis/full-project-conflict-quality-audit-inventory-2026-06-07.md
```

### Task 2: Top-Down Audit

Quote:

```text
Audit governance, entrypoints, configuration, launch scripts, CI, runtime manifests, dependencies, data stores, workers, UI/API workflows, destructive operations, GPU/runtime constraints, and known bug status from system shape to implementation.
```

Acceptance criteria:

- governance conflict matrix exists.
- architecture and workflow map exists.
- dependency/runtime drift table exists.
- high-risk module list exists with evidence.
- known bug/status consistency table exists.
- no conclusion relies on chat memory alone.

Minimum commands:

```powershell
git status --short --branch
rg -n "TODO|FIXME|HACK|XXX|probably|should work|verified|fixed|delete|remove|shutil.which|subprocess|QThread|cuda|torch|ffmpeg|ollama|deleted_at" .
rg --files
```

### Task 3: Bottom-Up Audit

Quote:

```text
Audit from tests, imports, symbols, call sites, failure branches, cleanup paths, cancellation paths, rollback paths, dead-code candidates, inactive UI wiring, and user workflow edges using a route independent from Task 2.
```

Acceptance criteria:

- test coverage map exists.
- call-site map exists for major workflows.
- dead-code and inactive-feature candidate list exists with import/call evidence.
- failure/cancel/cleanup/rollback risks are checked with direct evidence.
- pass 2 does not reuse pass 1 conclusions as proof.

Minimum commands:

```powershell
git status --short --branch
pytest --collect-only -q
rg -n "connect\(|triggered\.connect|clicked\.connect|emit\(|delete_selected|delete_all|restore|rollback|cancel|cleanup|finally|except Exception" ui services workers agents tests
```

### Task 4: Reviewer Challenge

Quote:

```text
Challenge audit findings for missing evidence, false positives, scope creep, and verification overclaims before final report.
```

Acceptance criteria:

- each proposed finding has evidence checked.
- unsupported findings are removed or downgraded.
- live-only claims are labeled not verified.
- optimization candidates are separated from bugs/blockers.

### Task 5: Final Audit Report And Fix-Plan Candidate

Quote:

```text
Write final audit report with scope, exclusions, coverage, findings, dependencies, task plan candidate, verification matrix, open questions, and not-checked list.
```

Acceptance criteria:

- final report includes scope and exclusions.
- final report includes pass 1 and pass 2 summaries.
- final report includes reviewer challenge summary.
- final report includes findings table.
- final report includes dependency/runtime table.
- final report includes dead-code/inactive-feature candidate table.
- final report includes optimization candidate table.
- final report includes fix-plan candidate grouped by risk and dependency order.
- final report includes verification matrix and explicit not-checked list.
- vault synthesis mirror is created.
- no bug is marked `fixed`.

Output:

```text
docs/superpowers/synthesis/full-project-conflict-quality-audit-final-2026-06-07.md
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\full-project-conflict-quality-audit-final-2026-06-07.md
```

## Stop Conditions

Stop and ask user if:

- code edit appears necessary
- dirty worktree appears with unknown changes
- evidence requires destructive or mutating command
- live verification is needed to classify a finding
- plan registry, active plan, decision, and vault mirror contradict each other
- multiple active plans appear

## Current Next Task

All audit tasks are static-complete as of 2026-06-07.

Next task:

```text
No implementation task. User decision required for any fix plan.
```

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-013` on 2026-06-09.

- Original plan: `PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07`
- Original open work: User decision for any fix plan after static audit.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.
