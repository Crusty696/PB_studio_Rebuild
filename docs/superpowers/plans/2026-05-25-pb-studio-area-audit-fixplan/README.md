# PB Studio Area Audit Fixplan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the approved findings from `PB-STUDIO-AREA-AUDIT-2026-05-24` in priority order, starting with B-348 so global pytest collection becomes usable again.

**Architecture:** Work one bug at a time. Each bug needs root-cause read, failing/proving test, minimal code/test change, targeted verification, Vault update, and honest live status. No `fixed` marker unless the relevant real app workflow is live-verified.

**Tech Stack:** Python 3.10 conda env `pb-studio`, pytest, PySide6 offscreen tests, SQLite/SQLAlchemy, Windows PowerShell, Vault notes.

---

## Scope

Authorized by user on 2026-05-25 after final audit synthesis.

This plan authorizes fixes for documented audit bugs B-348 through B-430. Work order is strict:

1. B-348 first.
2. High severity in bug-ID order unless a direct dependency forces a narrower prerequisite.
3. Medium severity in bug-ID order.
4. Low severity in bug-ID order.

No unrelated refactors, feature work, library swaps, model changes, Audio-V2 porting, or unlisted fixes.

## Current Task

### Task 1: B-348 pytest collect compatibility

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-348-pytest-collect-blocked-by-standalone-db-deep.md`

**Files:**
- Modify: `tests/test_db_deep.py`
- Maybe modify: `pyproject.toml` only if collection exclusion is chosen and preserves standalone runner behavior.
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-348-pytest-collect-blocked-by-standalone-db-deep.md`

- [ ] **Step 1: Read bug and current test file**

Read `tests/test_db_deep.py` top-level execution, repo-root calculation, and module-end `sys.exit`.

- [ ] **Step 2: Reproduce current failure**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest --collect-only -q
```

Expected before fix: pytest `INTERNALERROR` from `tests/test_db_deep.py` with `SystemExit`.

- [ ] **Step 3: Preserve standalone runner behavior**

Run direct script:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" tests/test_db_deep.py
```

Record exit code and main failure causes. Do not mark fixed based on standalone success unless command is green.

- [ ] **Step 4: Implement minimal collection-safe change**

Preferred fix: move standalone execution behind `if __name__ == "__main__":` and ensure pytest collection imports definitions without running the deep standalone suite. Keep standalone script callable.

- [ ] **Step 5: Verify collect**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest --collect-only -q
```

Expected after fix: no pytest `INTERNALERROR`.

- [ ] **Step 6: Verify standalone runner**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" tests/test_db_deep.py
```

Expected: no pytest import-time crash; standalone behavior is explicit. If standalone still reports existing DB assertions, document exact output and status as partial or code-fix-pending.

- [ ] **Step 7: Run targeted nearby tests**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest -q tests/test_database.py tests/database/test_project_notes_table.py tests/database/test_timeline_snapshot_table.py tests/database/test_schnitt_migrations_idempotent.py
```

- [ ] **Step 8: Vault and status**

Update B-348 with evidence. Use `fixed` only if collect is green and standalone intended behavior is verified. Otherwise use `code-fix-pending-live-verification` or keep `open` with exact blocker.

## Later Tasks

After Task 1, continue High bugs in order from the final audit:

- B-349 through B-430 according to `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\pb-studio-area-audit-final-2026-05-25.md`.
- For each bug: one root-cause read, one targeted failing/proving test, minimal fix, targeted verification, Vault update.

## Definition of Done

- Current bug has exact verification evidence.
- No `fixed` without real workflow where required.
- No unrelated files changed.
- Vault updated per bug.
- Commit only when a logically complete verified change exists and user workflow status is honestly described.

