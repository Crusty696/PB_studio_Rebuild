# PB Studio FFmpeg Resolver Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove documented bare FFmpeg/FFprobe calls from thumbnail and ingest paths so PB Studio uses the configured resolver consistently.

**Architecture:** Keep the existing central resolver in `services.startup_checks`. Add regression tests that monkeypatch resolver return values and assert subprocess commands use those paths. Then replace only the audited call sites from CQ-004 and CQ-005.

**Tech Stack:** Python 3.10, pytest, PySide6 widgets/workers, subprocess, existing `services.startup_checks.get_ffmpeg_bin()` / `get_ffprobe_bin()`.

---

plan_id: PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07
status: approved-for-implementation
mode: fix-plan
created: 2026-06-07
authorized_by_user: 2026-06-07 chat "mach das mit dem groesseren mehr wert und das die app weiter bringt"
source_audit: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07

## Scope

Fix these audited findings:

- CQ-004: `workers/video.py` and `ui/widgets/media_grid.py` call bare `"ffmpeg"` for thumbnails.
- CQ-005: `services/ingest_service.py` defines bare `_FFPROBE` / `_FFMPEG` environment fallbacks instead of central resolver.

Out of scope:

- Poetry/runtime-manifest cleanup.
- GUI visual changes.
- Dead-code removal.
- Vault `fixed` status changes.
- Full app live verification marker.

## File Map

- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Modify: `docs/superpowers/PLAN_REGISTRY.md`
- Modify: `docs/superpowers/AGENT_HANDOFF.md`
- Create: `docs/superpowers/plans/2026-06-07-ffmpeg-resolver-fix.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-058-ffmpeg-resolver-fix.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-ffmpeg-resolver-fix-2026-06-07.md`
- Modify: `workers/video.py`
- Modify: `ui/widgets/media_grid.py`
- Modify: `services/ingest_service.py`
- Create: `tests/test_ffmpeg_resolver_usage.py`
- Update: `C:\Brain-Bug\projects\pb-studio\log.md`

## Tasks

### Task 0: Governance Activation

Quote:

```text
Register and activate PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07 in repo governance and vault.
```

Acceptance criteria:

- `git status --short --branch` is clean or only current governance files are dirty.
- Branch is `codex/PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07`.
- Registry row exists.
- `ACTIVE_PLAN.md` selects exactly this plan.
- Vault decision exists.
- Vault plan mirror exists.
- `AGENT_HANDOFF.md` no longer claims the old active plan.

### Task 1: Regression Tests

Quote:

```text
Add regression tests proving frame extraction, media-grid thumbnail extraction, and ingest probing use configured FFmpeg/FFprobe resolver paths.
```

Acceptance criteria:

- Test for `workers.video.FrameExtractWorker.run()` monkeypatches `workers.video.get_ffmpeg_bin` to `C:\PB-Studio-Bin\ffmpeg.exe` and asserts `subprocess.run` receives that path as `cmd[0]`.
- Test for `ui.widgets.media_grid._ThumbWorker._extract()` monkeypatches `ui.widgets.media_grid.get_ffmpeg_bin` to `C:\PB-Studio-Bin\ffmpeg.exe` and asserts `subprocess.run` receives that path as `cmd[0]`.
- Test for `services.ingest_service._probe_video_meta()` monkeypatches `services.ingest_service.get_ffprobe_bin` to `C:\PB-Studio-Bin\ffprobe.exe` and asserts `subprocess.run` receives that path as `cmd[0]`.
- Tests do not call real FFmpeg/FFprobe.

Command:

```powershell
& "$env:USERPROFILE\miniconda3\Scripts\conda.exe" run -n pb-studio pytest tests/test_ffmpeg_resolver_usage.py -q
```

Expected before implementation:

```text
3 failed
```

### Task 2: Resolver Implementation

Quote:

```text
Replace audited bare FFmpeg/FFprobe binaries with central resolver calls without changing behavior beyond binary resolution.
```

Acceptance criteria:

- `workers/video.py` imports `get_ffmpeg_bin` from `services.startup_checks`.
- `FrameExtractWorker.run()` uses `get_ffmpeg_bin()` as first command item.
- `ui/widgets/media_grid.py` imports `get_ffmpeg_bin` from `services.startup_checks`.
- `_ThumbWorker._extract()` uses `get_ffmpeg_bin()` as first command item.
- `services/ingest_service.py` imports `get_ffprobe_bin` from `services.startup_checks`.
- `_probe_video_meta()` uses `get_ffprobe_bin()` as first command item.
- No new resolver abstraction is added.
- No unrelated FFmpeg paths are touched.

### Task 3: Verification

Quote:

```text
Run focused resolver tests, import smoke checks, and existing adjacent tests.
```

Acceptance criteria:

- Focused resolver tests pass.
- Existing ingest tests pass.
- Worker import smoke passes.
- Media grid import smoke passes.
- No live GUI verification is claimed.

Commands:

```powershell
& "$env:USERPROFILE\miniconda3\Scripts\conda.exe" run -n pb-studio pytest tests/test_ffmpeg_resolver_usage.py tests/test_services/test_ingest_service.py -q
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -c "import workers.video; import ui.widgets.media_grid; import services.ingest_service; print('imports ok')"
```

### Task 4: Vault And Commit

Quote:

```text
Record verification status in vault, update handoff state, and commit with honest verification body.
```

Acceptance criteria:

- Vault plan mirror marks tasks static/unit-complete as appropriate.
- `log.md` records tests and open live verification.
- Commit message says no live GUI verification.
- No bug file is marked `fixed`.

## Current Next Task

```text
No implementation task. Code fix pending live GUI verification.
```

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-004` on 2026-06-09.

- Original plan: `PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07`
- Original open work: Live GUI verification for media-grid thumbnail path, frame extraction path, and video ingest GUI workflow.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.
