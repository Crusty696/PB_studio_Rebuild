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
OTK-014: PB Studio Bugfix phase order F-1..F-30 / B-333..B-362.
```

## Consolidated Tasks

| new_task_id | priority | source_plan | source_status | transferred_work | evidence | status |
|---|---:|---|---|---|---|---|
| OTK-001 | 1 | ACTIVE_PLAN + AGENT_HANDOFF | conflict | Governance-Drift: ACTIVE_PLAN nannte Agent-Team-Skill-Plan, Handoff nannte FFmpeg-Resolver-Fix. Bereinigt am 2026-06-09; Handoff verweist jetzt auf diesen Masterplan und OTK-Taskfolge. | `docs/superpowers/ACTIVE_PLAN.md`; `docs/superpowers/AGENT_HANDOFF.md` | completed |
| OTK-002 | 1 | PB-STUDIO-AGENT-TEAM-SKILL-ARCHITECTURE-2026-06-08 | approved-for-implementation | User continuation release received; agent review found no blocking issue in created agent/team skill files. No claim that user read every file line-by-line. | Registry `next_allowed_task`; `.agents/skills/pb-agent-team-architect/SKILL.md`; `.agents/skills/pb-live-verify-orchestrator/SKILL.md`; `.agents/skills/pb-concurrency-strike-team/SKILL.md`; `.agents/skills/pb-release-readiness-team/SKILL.md` | completed-by-user-release |
| OTK-003 | 1 | PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07 | code-complete-live-pending | B-471 user review found real video placement gaps. 2026-06-09 fix: `repair_timeline_integrity()` now closes unlocked video gaps; `test55655` DB backed up and repaired from 7 gaps/1 overlap to 0/0. Autonomous GUI verification PASS: project opened through GUI, SCHNITT timeline ready, waveform, beat/anchor markers, thumbnails, zoom controls, cut list, and clip inspector observed. User explicitly approved `fixed` marker on 2026-06-09. | Registry; `wiki/bugs/B-471...`; `test_reports/B471_TIMELINE_GAP_REPAIR_2026-06-09.md`; `run_pytest_schnitt.bat`; `tests/test_services/test_apply_auto_edit_locked.py`; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md`; `test_reports/live_autonomous_20260609_otk003_*.png` | fixed |
| OTK-004 | 1 | PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07 | code-complete-live-pending | Filled checklist reports real GUI PASS for media-grid/FFmpeg path. Agent autonomous GUI run first gave PARTIAL PASS, then user gave broad status/workflow release and agent executed the missing import/live resolver path: Video import dialog opened, 1 MP4 selected, FolderImport and BrainV3Hashing finished, media table stayed populated with analyzed clips, no Traceback/ERROR/resolver failure found in checked logs. Empty card/grid observation was not reproduced. | Registry; Handoff; plan mirror; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md`; `test_reports/live_autonomous_20260609_otk004_*.png`; `test_reports/live_autonomous_20260609_otk004_import_dialog.png`; `test_reports/live_autonomous_20260609_otk004_after_import.png`; `logs/pb_studio.log` | fixed |
| OTK-005 | 1 | PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31 | code-complete-live-pending | B-462-A user `fixed` confirmation and optional Task 12 purge decision. | Registry; `wiki/bugs/B-462...`; `full-audit-fixplan-verification`. | open |
| OTK-006 | 1 | CONSULTING-TEAM-UND-LUECKEN-KONSOLIDIERUNG-2026-05-31 | code-complete-live-pending | B-439/B-440 App-Workflow-Live-Verify. | Registry; Vault mirror lines for B-439/B-440. | open |
| OTK-007 | 1 | PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25 | code-complete-live-pending | User/live verification of remaining `code-fix-pending-live-verification` bugs B-348..B-430. | Registry. | open |
| OTK-008 | 1 | SCHNITT-WORKSPACE-REDESIGN-2026-05-09 | code-complete-live-pending | Autonomous GUI verification PASS for navigation: Schnitt, Pacing/Anker, Audio, and RL Notes tabs opened; anchor list, Pacing controls, LUFS/key/stems panel, RL events list, timeline and cut list observed. 2026-06-09 substitute run with user-authorized `test55655`: SCHNITT reopened after app restart/project reload and RL Notes text persisted; `cut_rate_combo` crop stayed pixel-identical after hover+wheel-scroll (`diff_sum=0.0`); notes-editor undo returned exact original text after `Ctrl+Z`; Pacing regenerate expected QMessageBox appeared via UIA `Invoke()` and B-474 was corrected to `cannot-reproduce` as app bug. Formal Phase-12 completion is blocked because exact audio file `Crusty Progressive Psy Set2.mp3` was not found and the available Solo_Natur folder contains 124 MP4 files instead of the expected 103. | Registry; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md`; `test_reports/live_autonomous_20260609_otk008_*.png`; `docs/superpowers/synthesis/functional-test-otk008-test55655-substitute-2026-06-09.md`; `wiki/bugs/B-474...` | blocked-formal-dataset-missing-substitute-partial-pass |
| OTK-009 | 1 | SCHNITT-USABILITY-WIRING-REBUILD-2026-05-13 | code-complete-live-pending | Task 8 live verification and contradiction check completed on 2026-06-09. B-316..B-320 current Vault state is fixed. B-310 and B-313 were live-verified on `test55655`: SCHNITT timeline, thumbnails, cut list, audio metadata/stems/waveform, and sub-tab tooltip observed. | Registry; `bug-und-task-liste-2026-05-20`; `wiki/bugs/B-310...`; `wiki/bugs/B-313...`; `docs/superpowers/synthesis/functional-test-otk009-schnitt-usability-2026-06-09.md`; `test_reports/live_autonomous_20260609_otk009_*.png` | fixed |
| OTK-010 | 1 | BRAIN-V3-NVIDIA-2026-05-04 | code-complete-live-pending | 2026-06-09 follow-up verified Brain V3 boot health, GpuSerializer init, EmbeddingScheduler active, Brain V3 GUI panel, Brain V3 tests `37 passed`, isolated NVENC 1-frame encode, existing B-276 Brain+NVENC serializer live evidence, adopted D-035 Pacing decision, and B-370 GUI Auto-Edit with Studio-Brain flag on `test55655` producing 767 segments / 767 cuts and 1447 `mem_decision` rows. | Registry; `brain-v3-open-items-2026-05-20`; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md`; `docs/superpowers/synthesis/functional-test-otk010-brain-v3-nvidia-2026-06-09.md`; `test_reports/live_autonomous_20260609_otk010_brain_v3_panel.png`; `test_reports/live_autonomous_20260609_otk010_b370_gui_autoedit_done.png`; `logs/pb_studio.log` | fixed |
| OTK-011 | 1 | PB-STUDIO-AREA-AUDIT-2026-05-24 | code-complete-live-pending | Audit-only plan completed all 10 areas and final synthesis. User-approved follow-up fixplan already exists as `PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25`; actual remaining B-348..B-430 fix/live work is tracked separately as OTK-007. No app-code change for this decision task. | Registry; `docs/superpowers/plans/2026-05-24-pb-studio-area-audit/README.md`; `wiki/synthesis/pb-studio-area-audit-final-2026-05-25.md`; `docs/superpowers/plans/2026-05-25-pb-studio-area-audit-fixplan/README.md` | fixed |
| OTK-012 | 1 | PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31 | code-complete-live-pending | Read-only full project file audit completed. User decision already exists as D-055: full-project audit fixplan approved for implementation on 2026-05-31. Follow-up implementation plan `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` exists and its remaining open work is tracked separately as OTK-005. No app-code change for this decision task. | Registry; `wiki/decisions/D-055-full-project-audit-fixplan.md`; `docs/superpowers/plans/2026-05-31-full-project-audit-fixplan.md`; `wiki/synthesis/full-project-file-audit-final-2026-05-31.md` | fixed |
| OTK-013 | 1 | PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07 | approved-for-planning | Static conflict-quality audit completed. User decision exists as D-058 for the highest direct app-value follow-up: FFmpeg resolver fix for CQ-004/CQ-005. That follow-up plan was transferred to OTK-004 and its GUI import/resolver path was live-verified there. No new broad fixplan invented for remaining candidate-only findings. | Registry; conflict-quality final synthesis; `wiki/decisions/D-058-ffmpeg-resolver-fix.md`; `docs/superpowers/plans/2026-06-07-ffmpeg-resolver-fix.md`; OTK-004 evidence | fixed |
| OTK-014 | 2 | PB-STUDIO-BUGFIX-2026-05-23 | approved-for-implementation | Phase order F-1..F-30 / B-333..B-362, one task at a time. B-333/F-1 fixed 2026-06-09 after real GTX-1060/CUDA pipeline proved SigLIP VRAM drops 1723.6 MB -> 0.0 MB before RAFT. B-334/F-2 fixed 2026-06-09 after contract tests and live_gpu e2e proved SigLIP/RAFT run under `gpu_serializer`. B-335/F-3 fixed 2026-06-09 after weight-sum scorer regression. B-336/F-4 fixed 2026-06-09 after fp16 NaN-Guard tests and GTX-1060 SigLIP precision benchmark. B-337/F-5 fixed 2026-06-09 after live GUI proved SCHNITT ClipInspector effect controls visible. Next: B-338/F-6. GUI fixes stay live-pending until real workflow. | Registry; `wiki/bugs/B-333-vram-leak-stages-no-unload.md`; `wiki/bugs/B-334-gpu-lock-aware-dead.md`; `wiki/bugs/B-335-brain-v3-scorer-weight-normalization.md`; `wiki/bugs/B-336-model-manager-fp16-pascal.md`; `wiki/bugs/B-337-effects-feature-unreachable.md`; `test_reports/otk014_b333_live_gpu_20260609/b333_live_gpu_result.json`; `test_reports/otk014_b336_siglip_precision_20260609.md`; `test_reports/otk014_b337_schnitt_inspector_live_20260609.json`. | open |
| OTK-015 | 2 | PB-STUDIO-INTEGRATION-SIDE-EFFECTS-2026-05-23 | approved-for-implementation | Filled checklist reports PARTIAL: Quick Preview export started as H.264 1920x1080@30, disk precheck ok, render reached 70 percent then was aborted after about 6 minutes. Code path was inspected for h264_nvenc preference, 1-frame NVENC test, libx264 fallback, no AV1. Still open: completed export and exact runtime encoder string. | Registry; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md` | partial-live-verification |
| OTK-016 | 2 | PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20 | approved-for-implementation | Governance gate plus remaining open bugs: B-327, B-331, B-332, B-197, B-198, B-265 and any non-fixed bug still in Vault. | Registry; `bug-und-task-liste-2026-05-20`. | open |
| OTK-017 | 2 | Handoff / Vault bugs | mixed | B-458/B-459/B-460/B-463 user/live verification; B-464..B-468 open; B-469 monitoring; B-470 status drift; B-472 live verification. | `AGENT_HANDOFF.md`; `wiki/bugs/B-458...B-472`. | open |
| OTK-018 | 3 | AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17 | approved-for-planning | P0 Freeze And Snapshot before any Audio-V2 port; sandbox branch dirty/old, direct merge forbidden. | Registry. | open |
| OTK-019 | 3 | VIDEO-PIPELINE-ENGINE-2026-05-19 | approved-for-implementation | Filled checklist reports PARTIAL: outputs present/rendered, import and analysis already at 100 percent, timeline 768 clips, stems, beats/BPM 143.6, logs no errors. Still open: fresh end-to-end pipeline rerun with live progress and plan-doc phase determination. | Registry; plan `99_OPEN_QUESTIONS.md`; `90_LIVE_VERIFY.md`; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md` | partial-live-verification |
| OTK-020 | 3 | LLM-BACKEND-PLATFORM-2026-05-19 | user-authorized-fix-follow-up | B-473 Ollama local-agent connection recovery. Evidence: stale settings `http://legacy:8080` + `legacy-model`, local Ollama reachable on `localhost:11434`, full PB system prompt timed out beyond 120s, ChatDock watchdog was 60s. Fix: stale URL fallback, missing model reselect, compact GTX-1060 prompt budget, 180s ChatDock watchdog, settings reset with backup. Autonomous GUI verification PASS: ChatDock answered real message in UI and KI-Agent tasks finished. User explicitly approved `fixed` marker on 2026-06-09. | `wiki/bugs/B-473-ollama-local-agent-connection.md`; tests `test_local_agent_health_check.py`; standalone Agent smoke; `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md`; `test_reports/live_autonomous_20260609_otk020_*.png` | fixed |
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
