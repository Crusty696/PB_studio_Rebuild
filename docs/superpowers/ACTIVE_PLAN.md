# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-PERF-DB-CLEANUP-2026-07-12
repo_plan: docs/superpowers/plans/2026-07-12-perf-db-cleanup-plan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-perf-db-cleanup-2026-07-12.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-067-perf-db-cleanup.md
updated: 2026-07-13
worktree: Repo-Root (main) + Agent-Worktrees unter .claude/worktrees/
branch: main

## Why This Plan Is Active

User-Entscheidungen 2026-07-13 (Chat): (1) Perf-Plan JETZT starten,
Blocker (virt-M4-Sichtung) aufgehoben — Sichtung laeuft parallel.
(2) K6 Teil B entschieden: FK bleibt AUS -> Konsolidierungs-Plan
komplett code-complete-live-pending (nur noch User-Sichtung + fixed).

Ausfuehrungsmodus wie Konsolidierung (User-Auftrag "arbeite weiter wie
bisher"): parallele Worktree-Agenten mit disjunkten Datei-Mengen,
sequentielle Merges + Verify durch Hauptagent. Abweichung von der
urspruenglichen strikt-sequentiellen Reihenfolge im Plan-Doc ist damit
User-autorisiert. E9 (database/session.py Engine-Cache) laeuft NIE
parallel — als letzter Solo-Schritt nach allen Merges.

## Current Next Task

Keine offene Code-Task. E1-E10 sind committed und backend-verifiziert.
Offen bleiben reale GUI-/App-Livepfade, D-069 Voll-Package-/Installed-App-Test
und User-`fixed`. Abschlussbeleg:
`docs/superpowers/synthesis/perf-db-cleanup-abschluss-2026-07-13.md`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
