# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10
repo_plan: docs/superpowers/plans/2026-07-10-timeline-virtualisierung-plan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-timeline-virtualisierung-2026-07-10.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-066-timeline-virtualisierung.md
updated: 2026-07-10
worktree: Repo-Root (main)
branch: main

## Why This Plan Is Active

User-Entscheidung 2026-07-10 (Chat, Option "2" nach Plan-Aufsatz):
Implementierung der Timeline-/Grid-Virtualisierung starten.

Kontext: Am 2026-07-10 wurden alle Branches nach `main` konsolidiert
(origin gepusht) und saemtliche DB-Blocker im Workspace-Klick-Pfad gefixt
(9ddeec6, 7e0f96e; B-605-Crash-Fix 4254d5c). Profil-bewiesener Rest:
20-34s Qt-Show bei 1428 Cuts/375 Videos -> dieser Plan.

Vorgaenger-Plaene AUDIT-FIXPLAN + NEUBAUTEN-VOLLINTEGRATION sind
code-complete-live-pending (nur noch User-`fixed` offen); deren Worktrees
wurden bei der main-Konsolidierung entfernt.

## Current Next Task

M4 — Verify (hart): Profil-Lauf (M0-Harness) auf test33 gegen die
Abnahme-Kriterien (Klick < 2 s, kein Watchdog-Dump > 2 s); volle
Testsuite ist gruen (648 passed); Live-GUI-Check + User-Sichtung —
`fixed` setzt der User.

Stand 2026-07-10 spaet: M0-M3 KOMPLETT code-complete. Live-Verify-Rezept:
alte App (pid 8032, alter Stand) schliessen, Start mit
PB_STUDIO_FREEZE_PROBE=1 + PB_TIMELINE_PERF=1, test33 via Dialog oeffnen,
`python scripts/diag/verify_workspace_switch_perf.py --cycles 3`.
B-613 root-caused + Tests nachgezogen (ddd2293-Semantik, kein Produkt-Bug).

Stand 2026-07-10 abends: M0 fertig (50c6683). M1 Records +
Materialisierungs-Fenster + record-first Syncs code-complete
(TDD-Guards gruen, live-pending — User-App pid 8032 mit altem Stand
lief noch, kein paralleler App-Start wegen SQLite-Lock-Risiko).
Live-Verify: App neu starten (PB_STUDIO_FREEZE_PROBE=1,
PB_TIMELINE_PERF=1), test33 oeffnen, scripts/diag/
verify_workspace_switch_perf.py.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- `fixed` setzt nur der User nach Live-Test.
