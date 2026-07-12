# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-KONSOLIDIERUNG-2026-07-12
repo_plan: docs/superpowers/plans/2026-07-12-konsolidierung-plan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-konsolidierung-2026-07-12.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-068-konsolidierung-oberste-prioritaet.md
updated: 2026-07-12
worktree: Repo-Root (main)
branch: main

## Why This Plan Is Active

User-Entscheidung 2026-07-12 (Chat, /simplify Finding 6/7):
Konsolidierungs-Plan K1-K9 bekommt OBERSTE PRIORITAET und wird als
Erstes abgearbeitet — "auch wenn es ein anderer Agent machen muss".

Prioritaets-Kette: KONSOLIDIERUNG -> PERF-DB-CLEANUP (E1-E10, D-067)
-> weitere. Die virt-M4-User-Sichtung (fixed-Marker auf
PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10) ist reine User-Aktion
und laeuft parallel; sie blockiert diesen Plan nicht.

## Current Next Task

ALLE 9 TASKS CODE-COMPLETE (2026-07-13, main 277d2b9). Ausfuehrung:
5 parallele Worktree-Agenten + sequentielle Merges, je Task
Paritaets-Verify. Synthese:
docs/superpowers/synthesis/konsolidierung-abschluss-2026-07-13.md
(Vault-Mirror vorhanden).

OFFEN (nur User):
1. K6 Teil B: foreign_keys=ON im Auto-Edit-Pfad — expliziter
   User-Entscheid (STOP+ASK).
2. Live-Sichtung der 4 K8-Flows (siehe Synthese) + allgemeine
   App-Sichtung.
3. `fixed`-Marker auf dem Plan.

Danach naechster Plan: PB-STUDIO-PERF-DB-CLEANUP-2026-07-12 (E1-E10,
Blocker: virt-M4-User-fixed + Konsolidierung-User-fixed).

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Byte-/Ergebnis-Paritaet pro Task beweisen (Verify-Abschnitt im Plan).
- `fixed` setzt nur der User nach Live-Test.
