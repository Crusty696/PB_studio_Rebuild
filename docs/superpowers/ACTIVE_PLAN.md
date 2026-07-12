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

K9 — database/session.py:343-354: toten Monkey-Patch auf
vector_db_service.DB_DIR/DB_FILE entfernen (beide ohne Konsumenten,
Service nutzt Lazy-Getter _default_db_file). "_instance": None
(F-030 Singleton-Reset) BEHALTEN. Verify: Grep Tests auf
DB_FILE/DB_DIR-Import, pytest test_database + Vector-DB-Tests,
Live-App-Start + Projekt-Swap.

Danach strikt sequentiell: K4 -> K7 -> K5 -> K2 -> K3 -> K6 -> K1 -> K8
(Details im Repo-Plan). K6 Teil B (foreign_keys=ON) = STOP + ASK.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Byte-/Ergebnis-Paritaet pro Task beweisen (Verify-Abschnitt im Plan).
- `fixed` setzt nur der User nach Live-Test.
