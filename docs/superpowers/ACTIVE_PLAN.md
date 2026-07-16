# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
updated: 2026-07-16
worktree: Repo-Root (main) + Agent-Worktrees unter .claude/worktrees/
branch: main

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

Ueberwiegend liegt KEINE Agent-Code-Task offen — der Grossteil ist User-Live-Sichtung
+ `fixed`-Marker (Bucket 1) und User-Entscheidungen (Bucket 2). Falls Agent-Arbeit
gewuenscht: Bucket 4 (frei ausfuehrbar) zuerst — AUDIT A3/B1/B2/B3/B4/B7/B9,
PERF D-069, FREEZE-CRASH ab_compare + B-618-Rest. Bucket 3 (AUDIT/NEUBAUTEN/AUFRAEUM)
erst nach den jeweiligen User-Gates. Bucket 7 (b469/timeline-quality/brain-tooltip)
braucht Bug-File-Abgleich vor Einordnung.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
