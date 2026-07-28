# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
supplemental_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md
stability_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-076-stabilitaetsprogramm-current-head.md
updated: 2026-07-28
worktree: Repo-Root (main) + Agent-Worktrees unter .worktrees/
branch: main

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

`STAB-4 / B-726 RAFT-Direktpfad unter GPU-Execution-Lease`.

STAB-1-Teilgates sowie B-723/B-725/B-741 sind code-complete/live-pending.
Gemäß D-078 sind breite Suite-/Live-/GPU-Stressprüfungen bis Abschluss
restlicher Fixarbeit verschoben. B-726 schützt öffentliche RAFT-Direkt-
Inferenz; nur bei Codeänderung kleinsten betroffenen Fokuscheck ausführen.

Keine breite Suite vor Abschluss restlicher Root-Cause-Tasks. Erster Fehler im
kleinsten Fokuscheck stoppt nur diese Root-Cause-Task.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
