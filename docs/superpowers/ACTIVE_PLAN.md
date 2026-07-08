# PB Studio Active Plan (Worktree: .worktrees/vollintegration)

status: active
active_plan_id: PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-neubauten-vollintegration-plan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-neubauten-vollintegration-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-064-audit-fixplan-und-vollintegration.md
updated: 2026-07-08
worktree: .worktrees/vollintegration
branch: claude/NEUBAU-VOLLINTEGRATION-2026-07-07

## Why This Plan Is Active (in diesem Worktree)

User-Entscheidung 2026-07-07 (Chat, woertlich): "Gate aufheben, mach parallel
im eigenen Worktree — aber nach der Beendung des Plans und wenn alles fertig
getestet ist und funktioniert muss es automatisch mit dem main zusammengefuegt
und integriert werden, damit ich alles Neue und Gefixte in der App testen kann."

Parallel-Setup:
- Haupt-Worktree (Repo-Root): `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`
  (anderer Agent/Chat) auf `codex/OTK-021-source-consolidation-2026-06-22`.
- Dieser Worktree: NUR `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`
  auf `claude/NEUBAU-VOLLINTEGRATION-2026-07-07`.

Stand 2026-07-08: SCHNITT-Fixplan vom User live-verifiziert und `fixed`
(Haupt-Branch). M1 (Paket 2) komplett — Synthese:
`docs/superpowers/synthesis/neubau-vollintegration-m1-done-2026-07-08.md`.
Haupt-Branch-Stand 7114ac4 (A0, B1-B4, B7, A1) eingemergt; A2 lief im
Haupt-Worktree noch (dirty) und wird vor der Paket-1-Default-AN-Abnahme
nachgemergt.

## Verbindlicher Abschluss (User-Auftrag)

Nach Abarbeitung ALLER Tasks + gruenem Regressions-Gate (inkl.
SCHNITT-Garantien: Beat-Sync 100 %, exaktes Audio-Ende):
1. Aktuellen Haupt-Branch final einmergen, Konflikte aufloesen, volle
   Testsuite gruen.
2. Automatischer Merge zurueck in `codex/OTK-021-source-consolidation-2026-06-22`
   + Push — ohne weitere Rueckfrage (explizit autorisiert). `fixed` setzt
   danach der User.

## Parallel-Regeln

- T1.1-T1.6 (M2) laufen jetzt; Paket-1-Default-AN-Abnahme erst nach
  A2-Merge (kein Lernen auf degradierten Daten).
- GPU-Live-Verifies mit dem Haupt-Worktree zeitlich koordinieren
  (eine GTX 1060); eigene Test-Projektordner unter diesem Worktree.
- Vault-Eintraege immer mit Plan-ID `NEUBAU-VOLLINTEGRATION` kennzeichnen.

## Current Next Task

```text
M2 / T1.1 — Studio-Brain-Pacing-Pipeline aktivieren (USE-001):
Persistentes Setting + UI-Schalter (SettingsStore, Checkbox) statt nackter
Env-Var PB_USE_STUDIO_BRAIN_PIPELINE (Env bleibt Override). Default AUS bis
zur Paket-1-Abnahme nach A2-Merge. Verify: Auto-Edit-Lauf erzeugt
mem_pacing_run- + mem_decision-Zeilen; DecisionRecorder im Explorer sichtbar.
Danach T1.2 (use_brain_v3=True am Pipeline-Konstruktor, ans Setting
gekoppelt) -> T1.3 (SteerOverrideQueue-Consumer) -> T1.5 -> T1.4 -> T1.6.
```
