# PB Studio Agent Handoff

This file is a repository-local continuity checkpoint for all agents.

## Latest Governance Update

- **Date:** 2026-06-09
- **Active plan:** `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
- **Repo plan:** `docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md`
- **Vault mirror:** `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md`
- **Decision:** `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md`
- **Status:** previous registry plans with open work were marked `superseded` and transferred into OTK tasks. No app-code change. No product bug marked `fixed`.
- **OTK-001:** Governance drift in this handoff file was cleaned on 2026-06-09. Older FFmpeg/B-471/B-458/B-462/B-463 details remain represented in the OTK masterplan, not as active-plan authority here.
- **OTK-002:** Completed by user continuation release plus agent review. No blocking issue found in `.agents/skills/pb-agent-team-architect`, `pb-live-verify-orchestrator`, `pb-concurrency-strike-team`, or `pb-release-readiness-team`. No claim that the user read every file line-by-line.
- **OTK-003:** Agent-side check ran on 2026-06-09: existing layout screenshot inspected; waveform and thumbnails are visible, but many labels render as square glyphs in the captured image. `run_pytest_schnitt.bat` passed (`27 passed`). User readability/touchpad/real workflow review is still missing; no `fixed` marker.
- **OTK-020/B-473:** User authorized switching focus on 2026-06-09. Root cause evidence: app settings pointed at `http://legacy:8080` with `legacy-model`, while local Ollama answered on `localhost:11434`; full PB system prompt caused `OllamaClient.chat()` timeout beyond 120s; ChatDock watchdog was 60s. Code now falls back from stale configured URL to localhost, reselects missing model, caps LocalAgent system prompt for GTX-1060 latency, and uses a 180s ChatDock watchdog. User settings were reset to `http://localhost:11434` / `gemma3:4b` after backup. Standalone agent smoke returned `OK` in 67.34s. Real GUI/user chat workflow still pending; no `fixed` marker.
- **Filled checklist update 2026-06-09:** `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md` reports OTK-020, OTK-003, OTK-004, OTK-008 as GUI PASS; OTK-010, OTK-015, OTK-019 as PARTIAL; remaining listed tasks as decision/scope. The checklist explicitly says no agent-side `fixed` marker.
- **Autonomous GUI verification 2026-06-09:** Agent used real PB Studio GUI with `pywinauto`. OTK-020 PASS (ChatDock/Ollama UI answer, KI-Agent tasks finished); OTK-003 PASS (project `test55655`, SCHNITT timeline/waveform/thumbnails/zoom/cut list/inspector); OTK-004 PARTIAL PASS (media table and analyzed clips observed, no new import); OTK-008 PASS for GUI navigation (Pacing/Anker, Audio, RL Notes, Schnitt tabs). Evidence: `test_reports/live_autonomous_20260609_*.png`; Vault synthesis `wiki/synthesis/functional-test-otk-autonomous-gui-2026-06-09.md`. No `fixed` marker set.
- **Next task:** `OTK-020: B-473 Ollama local-agent connection recovery; autonomous GUI verification PASS, fixed marker pending explicit user status decision.`

## Current Protocol

1. Start every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1
   ```

2. End or switch every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_handoff.ps1
   ```

3. Source of truth order:

   - Git commits on the current branch.
   - `docs/superpowers/ACTIVE_PLAN.md`.
   - Vault living plan and `C:\Brain-Bug\projects\pb-studio\log.md`.
   - This file.

4. Chat history is not source of truth. If it is not in Git or Vault, next
   agent must treat it as unknown.

## Current Branch

`codex/B-471-timeline-usability-recovery-2026-06-07`

Latest local commit before OTK-001 cleanup:

```text
a5a52a5 chore(OTK): consolidate open tasks
```

Push status was not checked in OTK-001.

## Current Active Plan

See `docs/superpowers/ACTIVE_PLAN.md`.

Active plan:

```text
PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
```

Current next task:

```text
OTK-020: B-473 Ollama local-agent connection recovery; autonomous GUI verification PASS, fixed marker pending explicit user status decision.
```

Current OTK-020 status:

```text
autonomous-gui-pass-fixed-marker-pending: standalone service smoke green and autonomous GUI ChatDock/Ollama test passed. No `fixed` marker set by agent.
```

## Consolidated Open Work

All older active/inactive plan work is consolidated in:

```text
docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md
```

Use OTK task order only. Do not resume old registry plans directly.

## Required Handoff State

Handoff must be one of:

- clean commit;
- named stash with exact reason and path list;
- explicit user-approved dirty state documented in Vault and chat.

Unknown dirty changes block work.
