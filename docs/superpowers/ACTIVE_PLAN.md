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

M4-Rest — B-614 Cold-Start-Freeze fixen: Stem-Preview liest beim
Projekt-Open 4x ~1.4-GB-Stem-WAVs komplett (stem_track_widget) und
drueckt per GIL/IO den ersten Workspace-Zyklus (Lauf 4: MATERIAL-Show
9.3 s, worst_click 22.75 s). Hebel: downsampled Peek statt Vollread,
Thread-Drosselung, Cockpit-Readiness async. Danach Harness-Wiederholung.

Stand 2026-07-10 nacht: M0-M3 code-complete; M4-Fix-Runden 1-3 committed
(2763832 refresh_audio-Guard + CutList-Deferral, 477ed9f ORM-Kaskaden ->
Spalten-Queries, 1788a42 Zeitbudget-Materialisierung). 4 Harness-Laeufe
gefahren (pb-gui-tester, echte App, test33): Zyklen 1+2 GRUEN
(alle Klicks <= 1.2-1.7 s), worst_click 28.9 -> 22.75 s, max_block
25.7 -> 10.5 s, Abnahme (<= 2 s) noch NICHT erfuellt — Rest = Zyklus 0
(B-614). Ergebnisse: tests/qa_artifacts/workspace_switch_perf.json,
Vault log.md 20:37-21:2x.

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
