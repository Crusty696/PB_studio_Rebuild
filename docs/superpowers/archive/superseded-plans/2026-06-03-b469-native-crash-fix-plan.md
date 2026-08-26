# B-469 Fix Plan — Native Qt6Core crash on concurrent media-DB reload

> **⛔ SUPERSEDED 2026-07-16 — PLAN GESCHLOSSEN.** Bucket-7-Aufloesung: B-469 =
> `parked-not-reproducible-monitoring`. Offener Punkt in `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16`
> Bucket 6 (Sackgassen/parked), Decision D-071. Task-Text nur Historie.
> Aktuelle offene Arbeit: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

status: proposed (awaits user release)
plan_id: B-469-NATIVE-CRASH-FIX-2026-06-03
parent_plan: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
bug: wiki/bugs/B-469-native-qt6core-crash-concurrent-media-db-reload-after-double-import.md
created: 2026-06-03
owner: unassigned (David confirms `status: fixed`)

---

## 1. Problem (verified observation)

Native crash, no Python traceback: faulting module `Qt6Core.dll` 6.7.3.0,
exception `0xc0000409` (STATUS_STACK_BUFFER_OVERRUN / Qt fast-fail), WER events
1000/1001 at 2026-06-03 09:10:06. Captured live in
`logs/manual_test_20260603_090657.log` (ends abruptly mid MediaHashRegistry scan)
during a user manual-test session.

Trigger sequence (from session log): new project created (engine swap) →
folder imported **twice** in quick succession → ≥5 overlapping "Medien-DB laden"
tasks + BrainV3Hashing within ~25s → cascade of "Kooperativer Abbruch" → crash.

NOT B-462 (no delete) and NOT B-463 (vision verified clean same session).
Same class as prior concurrent grid/DB native crashes B-444 / B-449 / B-453.

## 2. Root cause — hypothesis (NOT proven to a line)

Faulting module is Qt6Core (not sqlite3/torch) → a **QObject/QThread lifecycle
race**: the rapid `cancel_task` cascade tearing down worker/QThread objects
(cross-thread `deleteLater`) racing with newly-started "Medien-DB laden"
workers, compounded by a project-switch engine swap while workers were
non-idle → a signal delivered to, or member access of, a C++ object already
freed by Qt → fast-fail inside Qt6Core.

Honest caveat: this is a strong, evidence-backed hypothesis, **not** confirmed
to a specific line. A deterministic repro and/or a symbolized crash dump
(Qt debug symbols) is required to prove the exact fault site. Phase 0 exists to
close that gap before claiming any fix works.

### Two independently-fixable concurrency gaps (verified by code read)

1. **Project switch is not idle-enforced.** `database/session.py` swaps the
   SQLAlchemy engine atomically on project switch but only logs
   "ensure all workers are idle to avoid DB inconsistency" — no enforcement.
   Workers were running during the switch.
2. **"Medien-DB laden" is not single-flight.** `ui/controllers/media_table.py`
   `_refresh_media_table` (line ~78) starts a fresh `DBFetchWorker` via
   `GlobalTaskManager.start_task` per call. The 200ms debounce
   (`_refresh_media_table_debounced`, line ~179) only coalesces bursts, so a
   steady completion stream piles up many concurrent worker tasks.

Lifecycle history: `services/task_manager.py` `start_task` (line ~190) /
`cancel_task` (line ~440) carry extensive documented `moveToThread` /
`deleteLater` / ACCESS_VIOLATION mitigations — the teardown path is the
suspected fault locus.

## 3. Constraints (binding)

- Only authorized changes; no while-I'm-here edits; STOP+ASK on doubt.
- TDD: failing test / repro first, then minimal fix.
- Do NOT modify existing working functions beyond what each task names.
- `status: fixed` is set by the **user** only, after live evidence.
- Vault update per sub-step (log.md + bug file + this plan mirror).
- GPU hard rule: not relevant here (no model/device change), keep it that way.
- Worktree hygiene: clean handoff per task; one task at a time.

## 4. Staged approach (risk-ascending)

Order chosen so the lowest-risk, highest-isolation change lands first and is
verified before touching the documented-fragile teardown path.

### Phase 0 — Deterministic repro harness (BLOCKING, no app-code change)

Goal: a runnable repro that triggers (or stress-triggers) the crash on the
CURRENT code, so any later fix can be shown to remove it.

- Build a headless/automated stress script that, on a temp project, rapidly:
  starts a new project (engine swap) + launches multiple concurrent
  "Medien-DB laden" `DBFetchWorker` tasks + fires `cancel_task` on a subset
  while new ones start — in a loop of N iterations.
- Run under the real Qt event loop (QApplication) like `tests/gui_harness.py`.
- Acceptance: reproduces the native crash within a bounded loop (record crash
  rate, e.g. "crashes in k/N runs"). If it cannot be made deterministic,
  document the achieved probabilistic rate and use that loop as the regression
  gate (pre-fix crashes ≥X%, post-fix 0 in M× the loop length).
- Deliverable: `tests/repro/test_b469_media_reload_crash_stress.py` (or a
  `scripts/` repro if it must run out-of-process to survive a crash). Decide
  in-process vs subprocess based on whether the crash kills the test runner
  (a native crash will — so a **subprocess harness that asserts exit code**
  is the robust form).

Gate: do not start Phase 1 until the repro reliably distinguishes crash vs
no-crash.

### Phase 1 — Gap 2: single-flight media-DB reload (LOW risk)

- Make `_refresh_media_table` single-flight: if a "Medien-DB laden" task is
  already pending/running, mark a `_reload_dirty` flag instead of starting a
  second worker; when the in-flight one finishes, re-run once iff dirty.
- Pure UI-controller change; no task_manager/session changes.
- TDD: unit test asserting N rapid `_refresh_media_table` calls start exactly
  one worker (mock `GlobalTaskManager.start_task`), and that a call arriving
  during an in-flight run schedules exactly one trailing re-run.
- Verify: targeted tests + default gate + re-run Phase 0 stress (expect crash
  rate to drop materially).

### Phase 2 — Gap 1: idle-enforce before project-switch engine swap (MED risk)

- Before the engine swap on project switch, drain or cancel-and-await active
  worker tasks (bounded wait), so no worker holds the old engine across the
  swap. Convert the existing warning into enforcement.
- TDD: test that a project switch requested while a fake worker is "running"
  waits/cancels before swapping (no swap-under-busy).
- Verify: targeted tests + default gate + Phase 0 stress with project-switch
  in the loop (expect crash rate → 0 if hypothesis holds).

### Phase 3 — Re-verify; decide if Phase 4 needed

- Run Phase 0 stress at M× length. If 0 crashes → propose `status: fixed`
  (user confirms after a real GUI manual double-import test).
- If crashes persist → Phase 4.

### Phase 4 (CONDITIONAL) — Gap C: cancel/teardown ordering hardening (HIGH risk)

- Only if Phases 1–2 do not eliminate the crash.
- Harden `cancel_task` / thread-finished cleanup so no `deleteLater` or signal
  delivery targets an object after its thread quit. Touch the documented-fragile
  path minimally, each change behind the Phase 0 gate.
- May require obtaining a symbolized Qt crash dump first to confirm the exact
  fault before editing this path (avoid blind changes to ACCESS_VIOLATION-prone
  code).

## 5. Acceptance criteria (per phase)

- Targeted tests green.
- Full default gate green (no regression).
- Phase 0 stress harness: crash rate 0 across the agreed run length.
- Real GUI manual test: create project + double folder import + concurrent
  reload no longer crashes; session log shows clean operation, no WER 1000/1001.
- `status: fixed` set by user only.

## 6. Risks / open questions

- Race is timing-dependent; a "0 crashes in M runs" gate is probabilistic, not a
  proof. State the residual risk honestly when proposing `fixed`.
- Phase 4 touches code with a documented native-crash history — highest
  regression risk; gate every edit.
- Single-flight (Phase 1) must not drop the final refresh (stale grid). The
  trailing-dirty re-run covers this; test it.
- Idle-enforce (Phase 2) must not deadlock the UI if a worker hangs — use a
  bounded wait + fallback cancel.

## 7. Out of scope

- No GPU/model changes. No vision-path changes (B-463 done).
- No unrelated refactors of task_manager beyond the named teardown fix.
