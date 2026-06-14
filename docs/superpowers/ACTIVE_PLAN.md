# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
repo_plan: docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md
vault_mirror: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md
decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md
updated: 2026-06-15

## Why This Plan Is Active

CRF `PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12` finished its agent-executable fix waves.
Vault mirror `plan-consulting-review-fixplan-2026-06-12.md` records B-498..B-520 as fixed after user/live verification and B-523..B-529 as fixed after user release.

CRF remaining items are user decisions only:

- CRF-D1: Brain v1/v2/v3 deprecation direction.
- CRF-D2: Vault sync strategy.
- CRF-D3: cu121/torch-2.x migration and requirements archival.

Those decisions are not app-code implementation tasks and must not be executed by an agent without a concrete user choice.

## Current Next Task

```text
OTK-021 Tier 3 next subtask: 34 Project-Export + Import. Tier 1-2 plus
Tier 3/30 Storage-Migration-Service, 31 SCHNITT-Audio-Adapter,
32 Cross-Project-Reuse UX, and 33 Storage-Browser UI code/tests completed
by 2026-06-15. Product live verification remains pending. DG-001 remains
mandatory before fixed/release status.
```

## Agent Behavior

- Use only `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` as working authority.
- Do not resume superseded source plans directly.
- Do not work multiple OTK tasks in parallel in this worktree.
- Do not mark product bugs `fixed` without real live verification and explicit user confirmation.
- If the user asks for parallel teams, use them only for read-only analysis or separate worktrees after a single task is selected; no parallel half-finished app-code work in this repo directory.
