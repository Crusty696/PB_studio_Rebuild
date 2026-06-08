# PB Studio Agent Team Skill Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create evidence-backed PB-Studio agent and team files for large complex work, with clear hierarchy, strict governance alignment, and reusable specialization boundaries.

**Architecture:** Treat this as meta-infrastructure work, not app-feature work. First inventory existing PB-Studio skills, current recurring failure clusters, and missing orchestration gaps. Then design a small, explicit agent roster with one top-level orchestrator and narrowly scoped specialist teams. Every created agent file must inherit AGENTS.md truth rules, plan governance, live-verification discipline, and GTX-1060/CUDA constraints.

**Tech Stack:** Markdown skill files under `.agents/skills/`, repo governance docs, vault decision/synthesis notes, git worktree hygiene, existing PB-Studio specialist skills.

---

plan_id: PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08
status: approved-for-implementation
mode: meta-governance-skill-build
created: 2026-06-08
authorized_by_user: 2026-06-08 chat
scope_type: skill-and-team-files-only

## Scope

In scope:

- New agent/team skill files under `.agents/skills/` for large complex PB-Studio work.
- Hierarchical orchestration design for multi-agent execution.
- Skill docs for live verification, concurrency/race handling, release readiness, and cross-team coordination where evidence shows recurring need.
- Repo governance updates needed to authorize and track this meta-work.
- Vault decision/synthesis/log entries for this plan.

Out of scope:

- App code fixes outside files required to support skill/team authoring.
- Any `status: fixed` claim for product bugs.
- Dependency swaps, model changes, architecture refactors in app code.
- Silent changes to unrelated existing skills.

## Evidence Basis

Recurring problem clusters already documented in repo governance and verification handoff:

- Chat/agent concurrency and stale-worker bugs B-409..B-417.
- Export/Convert/FFmpeg/NVENC policy bugs B-393..B-408 and B-401..B-406.
- Timeline/waveform/thumbnail/live-verify loops B-384..B-391 and B-471/B-472.
- Packaging/live-smoke gaps B-421..B-430.
- Repeated project rule pressure around plan authority, user-only `fixed`, and vault honesty.

These clusters justify dedicated orchestrators and specialist teams instead of ad-hoc prompting.

## File Map

- Modify: `docs/superpowers/PLAN_REGISTRY.md`
- Modify: `docs/superpowers/ACTIVE_PLAN.md`
- Create: `docs/superpowers/plans/2026-06-08-agent-team-skill-architecture.md`
- Create: `.agents/skills/pb-live-verify-orchestrator/SKILL.md`
- Create: `.agents/skills/pb-concurrency-strike-team/SKILL.md`
- Create: `.agents/skills/pb-release-readiness-team/SKILL.md`
- Create: `.agents/skills/pb-agent-team-architect/SKILL.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-060-agent-team-skill-architecture.md`
- Create: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-agent-team-skill-architecture-2026-06-08.md`
- Modify: `C:\Brain-Bug\projects\pb-studio\log.md`

## Tasks

### Task 0: Governance Activation

Quote:

```text
Register and activate PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08 in repo governance and vault.
```

Acceptance criteria:

- Registry row exists.
- `ACTIVE_PLAN.md` selects exactly this plan.
- Vault decision exists.
- Vault mirror exists.
- Scope states meta-work only, no app-code bugfix claims.

### Task 1: Inventory Existing Skill Surface And Gaps

Quote:

```text
Inventory current PB-Studio specialist skills, team patterns, and recurring failure clusters to prove which new agent files are actually needed.
```

Acceptance criteria:

- Existing relevant skills are listed with responsibilities and overlap.
- Missing orchestration gaps are explicit.
- Each proposed new agent has at least one concrete recurring evidence source.
- No generic or redundant agent is proposed.

### Task 2: Define Agent Roster And Hierarchy

Quote:

```text
Design a minimal hierarchical roster for large complex PB-Studio work and map command boundaries between director, team leads, and specialists.
```

Acceptance criteria:

- One top-level architect/director role defined.
- Live-verify, concurrency, and release-readiness teams each have clear trigger conditions.
- Ownership boundaries are explicit; no two teams own same state simultaneously.
- Escalation path and stop conditions are documented.

### Task 3: Author Agent Files With Local Rule Inheritance

Quote:

```text
Write the new agent/team skill files so they inherit AGENTS.md truth rules, plan governance, verification discipline, vault duties, and GPU constraints.
```

Acceptance criteria:

- New skill files are in German where user-facing behavior is defined.
- Each file has clear trigger description.
- Each file forbids overclaiming `fixed`/`verified`.
- Each file references exact next specialist/team choices where needed.
- No file claims unsupported tooling or parallel ownership.

### Task 4: Validate Against Writing-Skills Standard

Quote:

```text
Review the new skill files against writing-skills quality rules and close obvious loopholes before handoff.
```

Acceptance criteria:

- Descriptions are search-usable and trigger-based.
- Repeated loopholes are explicitly blocked.
- Scope/ownership ambiguities are removed.
- Redundant overlap with existing PB skills is called out.

### Task 5: Vault, Memory, Handoff

Quote:

```text
Record the governance decision, created skill files, remaining gaps, and next execution path in vault, repo memory, and user report.
```

Acceptance criteria:

- Vault synthesis updated.
- Vault log entry appended.
- Automation memory updated.
- User report distinguishes created files vs unverified future usefulness.

## Current Next Task

```text
User review of created agent/team skill files
```

## 2026-06-08 Progress

- Task 0 completed: governance activation done in repo and vault.
- Task 1 completed: existing evidence clusters and existing PB skills were inventoried against current gaps.
  - Existing direct specialists already cover: live status (`pb-live-verify-chief`), GUI execution (`pb-functional-tester`), regression retest (`pb-workflow-regression-chief`), GPU/CUDA gates (`pb-gpu-pipeline-gatekeeper`), Qt UI/thread work (`pb-ui-specialist`), packaging (`qt-packaging`), and FFmpeg command/runtime concerns (`ffmpeg`).
  - Missing layer was not another low-level specialist; missing layer was reusable team ownership above them.
  - Concrete gap clusters used as evidence: `docs/VERIFY_HANDOVER_2026-05-29.md`, B-409..B-417 chat concurrency, B-393..B-408 export/convert, B-421..B-430 packaging, B-384..B-391 and B-471/B-472 timeline/live-verify loops.
- Task 2 completed: roster fixed to one architect plus three teams, avoiding duplicate ownership.
- Task 3 completed: these new skill files were created:
  - `.agents/skills/pb-agent-team-architect/SKILL.md`
  - `.agents/skills/pb-live-verify-orchestrator/SKILL.md`
  - `.agents/skills/pb-concurrency-strike-team/SKILL.md`
  - `.agents/skills/pb-release-readiness-team/SKILL.md`
- Task 4 completed as self-review only:
  - descriptions are trigger-based
  - each file forbids overclaiming `fixed` / `verified`
  - ownership boundaries are explicit
  - overlap stays above existing specialists, not beside them
- Task 5 completed for documentation:
  - vault log updated
  - automation memory updated

## Honest Limits

- No subagent pressure-test run yet against these new skill files.
- No commit yet.
- No claim that the new teams are field-proven; current status is authored and documented.

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-002` on 2026-06-09.

- Original plan: `PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08`
- Original open work: User review of created agent/team skill files.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.
