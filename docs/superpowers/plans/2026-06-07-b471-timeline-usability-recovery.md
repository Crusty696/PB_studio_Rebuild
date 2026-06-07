# B-471 Timeline Usability Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SCHNITT timeline usable in the live app: stable zoom lanes, visible audio waveform, visible video thumbnails, understandable pacing controls and tooltips.

**Architecture:** Treat the 2026-06-07 user screenshot as live evidence that previous B-471 stages did not solve the real workflow. First reproduce and pin root causes with focused tests around `ui/timeline.py` and SCHNITT widgets, then apply narrow UI fixes in value order. Do not touch pacing engine scoring until the visible timeline surface is usable.

**Tech Stack:** Python 3.10, PySide6/QGraphicsView, pytest/pytest-qt, SQLite timeline rows, existing B-471 thumbnail/waveform async loaders.

---

plan_id: PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07
status: code-complete-live-pending
mode: fix-plan
created: 2026-06-07
authorized_by_user: 2026-06-07 chat screenshot/report
source_bug: B-471

## Scope

In scope:

- Timeline zoom/fit must keep A1 and V1 lanes visible and vertically stable.
- Audio timeline item must show real waveform when waveform data exists; if missing, UI must say why.
- Video timeline items must show real thumbnails when file paths exist; if missing, UI must say why.
- Pacing & Anker panel must explain controls with action-oriented labels/tooltips.
- Report live verification status honestly.

Out of scope:

- Pacing scoring algorithm changes.
- Export/render changes.
- New model/dependency changes.
- `status: fixed` without user-confirmed live workflow.

## File Map

- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Modify: `docs/superpowers/PLAN_REGISTRY.md`
- Create: `docs/superpowers/plans/2026-06-07-b471-timeline-usability-recovery.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-059-b471-timeline-usability-recovery.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-b471-timeline-usability-recovery-2026-06-07.md`
- Modify: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-471-timeline-quality-cluster-gaps-thumbnails-zoom-freeze.md`
- Modify: `ui/timeline.py`
- Modify: `ui/workspaces/schnitt/timeline_shell.py`
- Modify: `ui/workspaces/schnitt/tab_pacing_anker.py`
- Add/modify focused tests under `tests/ui/` and `tests/test_ui/`
- Update: `C:\Brain-Bug\projects\pb-studio\log.md`

## Tasks

### Task 0: Governance Activation

Quote:

```text
Register and activate PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07 in repo governance and vault.
```

Acceptance criteria:

- Branch is `codex/B-471-timeline-usability-recovery-2026-06-07`.
- Registry row exists.
- `ACTIVE_PLAN.md` selects exactly this plan.
- Vault decision exists.
- Vault mirror exists.
- B-471 contains the 2026-06-07 screenshot/user-report addendum.

### Task 1: Reproduce And Pin Timeline Surface Failures

Quote:

```text
Add focused failing tests for lane stability, audio waveform visibility, video thumbnail visibility, and pacing tooltip usefulness.
```

Acceptance criteria:

- Test proves zoom/fit path keeps track lane Y positions stable and visible.
- Test proves audio clips with waveform data render a waveform child/item instead of only a flat bar.
- Test proves video clips with resolvable file path request/render thumbnails beyond placeholder.
- Test proves pacing controls have explanatory tooltips naming effect, when to use, and result.
- Tests run before implementation and fail for the current broken behavior where possible.

### Task 2: Timeline Lane And Zoom Recovery

Quote:

```text
Fix zoom/fit behavior so A1 and V1 stay visible, vertically stable, and not squeezed out of the viewport.
```

Acceptance criteria:

- No `fitInView(...KeepAspectRatio)` path may make track lanes vertically tiny.
- Zoom buttons and wheel zoom update horizontal scale without moving tracks out of view.
- Visible scene rect includes lane labels and enough lane padding.
- Focused lane tests pass.

### Task 3: Audio Waveform And Video Thumbnail Recovery

Quote:

```text
Make timeline audio waveform and video thumbnails visible or explicitly explain missing data in the UI.
```

Acceptance criteria:

- Audio timeline entries with waveform data show waveform content, not just blue rectangle.
- Audio entries without waveform data display a clear short overlay such as `Waveform fehlt - Audioanalyse starten`.
- Video entries with file path request and display thumbnails.
- Video entries without thumbnail/path display a clear short reason.
- Focused thumbnail/waveform tests pass.

### Task 4: Pacing Panel And Tooltip Recovery

Quote:

```text
Rewrite SCHNITT pacing controls and tooltips so a user can understand what each control changes, when to use it, and what result to expect.
```

Acceptance criteria:

- Pacing controls have tooltips with: effect, when to use, result.
- Main regenerate button tooltip states whether it rebuilds timeline and what can change.
- Timeline toolbar buttons explain zoom impact.
- No decorative copy; text is short and action-oriented.

### Task 5: Verification, Vault, Commit

Quote:

```text
Run focused tests, restart app, verify the real timeline workflow, document results in repo and vault, and commit with honest status.
```

Acceptance criteria:

- Focused tests pass.
- App restarted.
- SCHNITT timeline opened on real project.
- Zoom in/out/fit checked visually.
- A1 waveform and V1 thumbnails checked visually.
- Pacing tooltips checked visually.
- Test report exists under `test_reports/` and vault mirror.
- No `fixed` marker unless user confirms.

## Current Next Task

```text
Task 5 Verification, Vault, Commit
```

## 2026-06-07 Code-Complete Status

- Task 1: focused tests added; baseline run against `HEAD` failed for lane fit, thumbnail width, missing waveform overlay, weak pacing tooltip, weak timeline toolbar tooltip (`5 failed, 2 passed`).
- Task 2: code-complete; horizontal fit now avoids vertical `fitInView` squeezing.
- Task 3: code-complete; video thumbnail width no longer capped to 220 px for long clips, and audio clips without waveform show `Waveform fehlt - Audioanalyse starten`.
- Task 4: code-complete; SCHNITT timeline and pacing tooltips now state effect, when to use, and result.
- Task 5: focused tests and import smoke passed. App restarted, but real live timeline verification is blocked because the app reported no active project.

Status remains `code-complete-live-pending`, not `fixed`.

## 2026-06-07 Rekordbox Waveform Follow-up

- User live-tested `1966e94` and reported the timeline still looked unchanged.
- Research reference: rekordbox supports `Blue`, `RGB`, and `3Band` waveform display; 3Band depends on suitable analysis data.
- Root cause found: previous tests proved waveform item existence, not visibility. Waveform z-order was behind the audio clip, and async child waveform used `ItemStacksBehindParent`.
- Follow-up code fix: waveform/beatgrid now paints above the audio clip fill; timeline lanes are 80 px high; zoom buttons are touchpad-sized; zoom button step is 15 percent; video clips show `Thumbnail laedt` or `Thumbnail fehlt - Datei fehlt`.
- Verification: focused tests `25 passed`; `run_pytest_schnitt.bat` `23 passed`; affected py_compile passed; `from main import PBWindow` returned `OK` with GPU readiness warning.
- Additional live-test report `test_reports/b471_live_test55655.json`: project `test55655` blocked by running background tasks.
- Live verification remains open on a real active project.
