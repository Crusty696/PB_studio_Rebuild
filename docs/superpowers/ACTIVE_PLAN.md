# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
supplemental_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md
updated: 2026-07-27
worktree: Repo-Root (main) + Agent-Worktrees unter .claude/worktrees/
branch: main

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

R1 / B-727 (P0): `tests/conftest.py:_guarded_connect(database, ...)`
reparieren. Der Parameter `database` shadowt das Projektmodul; beim Aufbau des
Blockierfehlers wirft `database.engine` ein `AttributeError`, das der breite
`except Exception` schluckt. Dadurch kann `original_connect()` die reale
Projekt-DB weiter oeffnen.

Zuerst RED-Test: Real-DB-Ziel muss `RuntimeError` liefern und der gemockte
`original_connect` muss 0 Calls sehen. Danach Fokus-/Subprozess-Test plus
SHA/Laenge/mtime aller kanonischen `pb_studio.db`. Erst nach diesem Beweis
CI-identische Vollsuite.

Anschliessende Reihenfolge laut D-075: B-732, B-733, B-734, B-737, B-738,
B-735/B-736, Live-Wirkungsbeweis, dann restliche B-709…B-729.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
