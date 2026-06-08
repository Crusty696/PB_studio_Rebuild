# Offene Tasks Konsolidierung Masterplan 2026-06-09

plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
status: approved-for-implementation
owner: pb-plan-governor
created: 2026-06-09
authorized_by_user: 2026-06-09 chat
scope_type: governance-task-consolidation

## Purpose

Kanonischer Masterplan fuer offene PB-Studio-Arbeit aus Repo-Planen, Vault-Mirrors, Bugfiles und Handoff. Alte Quellplane bleiben als Quellen erhalten, werden aber nicht mehr als Arbeitsfokus genutzt.

Keine App-Code-Aenderung ist durch diese Konsolidierung erfolgt. Kein Produkt-Bug wurde auf `fixed` gesetzt.

## Transfer Rules

- Task gilt als offen, wenn Registry, Plan, Vault-Mirror, Bugfile oder Handoff `open`, `blocked`, `pending`, `live pending`, `code-fix-pending-live-verification`, unchecked checkbox, `User decision required`, `live verification pending`, `ausstehend` oder vergleichbare klare Formulierung nennt.
- Task wird nicht uebernommen, wenn eine neuere Quelle eindeutig `fixed` plus Live-Beleg zeigt oder der Task bereits mit Zielplan/Task-ID superseded wurde.
- Widerspruch bleibt sichtbar als `needs-human-decision`; keine Annahme.
- Status `fixed` bleibt user-only.

## Current Next Task

```text
OTK-003: B-471 user review of layout recovery; real app/user workflow still not fixed.
```

## Consolidated Tasks

| new_task_id | priority | source_plan | source_status | transferred_work | evidence | status |
|---|---:|---|---|---|---|---|
| OTK-001 | 1 | ACTIVE_PLAN + AGENT_HANDOFF | conflict | Governance-Drift: ACTIVE_PLAN nannte Agent-Team-Skill-Plan, Handoff nannte FFmpeg-Resolver-Fix. Bereinigt am 2026-06-09; Handoff verweist jetzt auf diesen Masterplan und OTK-Taskfolge. | `docs/superpowers/ACTIVE_PLAN.md`; `docs/superpowers/AGENT_HANDOFF.md` | completed |
| OTK-002 | 1 | PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08 | approved-for-implementation | User continuation release received; agent review found no blocking issue in created agent/team skill files. No claim that user read every file line-by-line. | Registry `next_allowed_task`; `.agents/skills/pb-agent-team-architect/SKILL.md`; `.agents/skills/pb-live-verify-orchestrator/SKILL.md`; `.agents/skills/pb-concurrency-strike-team/SKILL.md`; `.agents/skills/pb-release-readiness-team/SKILL.md` | completed-by-user-release |
| OTK-003 | 1 | PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07 | code-complete-live-pending | B-471 user review of layout recovery; real app/user workflow still not `fixed`. | Registry; `wiki/bugs/B-471...`; plan mirror. | open |
| OTK-004 | 1 | PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07 | code-complete-live-pending | Live GUI verification for media-grid thumbnail path, frame extraction path, and video ingest GUI workflow. | Registry; Handoff; plan mirror. | open |
| OTK-005 | 1 | PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31 | code-complete-live-pending | B-462-A user `fixed` confirmation and optional Task 12 purge decision. | Registry; `wiki/bugs/B-462...`; `full-audit-fixplan-verification`. | open |
| OTK-006 | 1 | CONSULTING-TEAM-UND-LUECKEN-KONSOLIDIERUNG-2026-05-31 | code-complete-live-pending | B-439/B-440 App-Workflow-Live-Verify. | Registry; Vault mirror lines for B-439/B-440. | open |
| OTK-007 | 1 | PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25 | code-complete-live-pending | User/live verification of remaining `code-fix-pending-live-verification` bugs B-348..B-430. | Registry. | open |
| OTK-008 | 1 | SCHNITT-WORKSPACE-REDESIGN-2026-05-09 | code-complete-live-pending | Phase 12 live verification / user confirmation path. | Registry. | open |
| OTK-009 | 1 | SCHNITT-USABILITY-WIRING-REBUILD-2026-05-13 | code-complete-live-pending | Task 8 live verification, then B-316..B-320 order only if still contradicted by current vault state. | Registry; `bug-und-task-liste-2026-05-20` marks B-316..B-320 fixed, so only contradiction check remains. | needs-human-decision |
| OTK-010 | 1 | BRAIN-V3-NVIDIA-2026-05-04 | code-complete-live-pending | Phase 1-3 App-Sync/live pending; Pre-Phase-4 PacingConfig spike; NVENC parallel and real DJ-mix validation. | Registry; `brain-v3-open-items-2026-05-20`. | open |
| OTK-011 | 1 | PB-STUDIO-AREA-AUDIT-2026-05-24 | code-complete-live-pending | User-approved fix plan / live-verification decision after audit-only completion. | Registry. | open |
| OTK-012 | 1 | PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31 | code-complete-live-pending | User decision for any fix or verification plan. | Registry. | open |
| OTK-013 | 1 | PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07 | approved-for-planning | User decision for any fix plan after static audit. | Registry; conflict-quality final synthesis. | open |
| OTK-014 | 2 | PB-STUDIO-BUGFIX-2026-05-23 | approved-for-implementation | Phase order F-1..F-30 / B-333..B-362, one task at a time. GUI fixes stay live-pending until real workflow. | Registry. | open |
| OTK-015 | 2 | PB-STUDIO-INTEGRATION-SIDE-EFFECTS-2026-05-23 | approved-for-implementation | Task 2: Export-NVENC absichern (Befund 1). | Registry. | open |
| OTK-016 | 2 | PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20 | approved-for-implementation | Governance gate plus remaining open bugs: B-327, B-331, B-332, B-197, B-198, B-265 and any non-fixed bug still in Vault. | Registry; `bug-und-task-liste-2026-05-20`. | open |
| OTK-017 | 2 | Handoff / Vault bugs | mixed | B-458/B-459/B-460/B-463 user/live verification; B-464..B-468 open; B-469 monitoring; B-470 status drift; B-472 live verification. | `AGENT_HANDOFF.md`; `wiki/bugs/B-458...B-472`. | open |
| OTK-018 | 3 | AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17 | approved-for-planning | P0 Freeze And Snapshot before any Audio-V2 port; sandbox branch dirty/old, direct merge forbidden. | Registry. | open |
| OTK-019 | 3 | VIDEO-PIPELINE-ENGINE-2026-05-19 | approved-for-implementation | Continue from first unchecked/unfinished phase; open questions and live verify remain. | Registry; plan `99_OPEN_QUESTIONS.md`; `90_LIVE_VERIFY.md`. | open |
| OTK-020 | 3 | LLM-BACKEND-PLATFORM-2026-05-19 | approved-for-planning | Planning/review only; caller migration restrictions; open questions and live verify remain. | Registry; plan `99_OPEN_QUESTIONS.md`; `90_LIVE_VERIFY.md`; `61_LIVE_VERIFY_USER.md`. | open |
| OTK-021 | 3 | GLOBAL-STORAGE-PROVENANCE-2026-05-19 | approved-for-planning | Planning/review only until prerequisites; open implementation/live-verify plan files remain. | Registry. | open |
| OTK-022 | 3 | COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22 | approved-for-implementation | Phase 1 workflow-first reference audit from `30_Workflows\Migration_Setup.md`. | Registry. | open |

## Source Plan Archive Map

All 20 previous registry plans were checked for open work and transferred into this masterplan. Each source plan and each Vault mirror gets a `Superseded / Task Transfer` marker. Work must continue from this masterplan only.

| source_plan | master_task |
|---|---|
| BRAIN-V3-NVIDIA-2026-05-04 | OTK-010 |
| SCHNITT-WORKSPACE-REDESIGN-2026-05-09 | OTK-008 |
| SCHNITT-USABILITY-WIRING-REBUILD-2026-05-13 | OTK-009 |
| AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17 | OTK-018 |
| PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20 | OTK-016 |
| COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22 | OTK-022 |
| PB-STUDIO-AREA-AUDIT-2026-05-24 | OTK-011 |
| PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25 | OTK-007 |
| VIDEO-PIPELINE-ENGINE-2026-05-19 | OTK-019 |
| LLM-BACKEND-PLATFORM-2026-05-19 | OTK-020 |
| GLOBAL-STORAGE-PROVENANCE-2026-05-19 | OTK-021 |
| PB-STUDIO-BUGFIX-2026-05-23 | OTK-014 |
| PB-STUDIO-INTEGRATION-SIDE-EFFECTS-2026-05-23 | OTK-015 |
| CONSULTING-TEAM-UND-LUECKEN-KONSOLIDIERUNG-2026-05-31 | OTK-006 |
| PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31 | OTK-012 |
| PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31 | OTK-005 |
| PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07 | OTK-013 |
| PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07 | OTK-004 |
| PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07 | OTK-003 |
| PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08 | OTK-002 |

## Verification Required After Governance Edit

- `git diff --check`
- check that every `superseded` registry row has a source transfer marker
- check every OTK task has source evidence
- check no `fixed` marker was newly set
- `ACTIVE_PLAN.md` must select exactly this plan
- Vault refresh/search must find this plan
