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

K4 — subprocess_kwargs: Helper aus startup_checks.py:149 oeffentlich
machen (bzw. nach services/ffmpeg_utils), ~25 Inline-Stellen umstellen
(Liste im Repo-Plan). Pro Datei ein Edit; Verify: ruff+compile, ein
realer ffmpeg-Aufruf pro betroffenem Service (kein Konsolen-Fenster,
Rueckgabe identisch).

Erledigt: K9 (618a5ca) — toter VectorDB-Konstanten-Patch raus,
F-030-Reset + H-6-close verifiziert (27/27 Tests + Live-Skript).

Danach strikt sequentiell: K7 -> K5 -> K2 -> K3 -> K6 -> K1 -> K8
(Details im Repo-Plan). K6 Teil B (foreign_keys=ON) = STOP + ASK.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Byte-/Ergebnis-Paritaet pro Task beweisen (Verify-Abschnitt im Plan).
- `fixed` setzt nur der User nach Live-Test.
