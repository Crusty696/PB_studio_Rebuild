# PB Studio Active Plan (Worktree: .worktrees/vollintegration)

status: active
active_plan_id: PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-neubauten-vollintegration-plan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-neubauten-vollintegration-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-064-audit-fixplan-und-vollintegration.md
updated: 2026-07-07
worktree: .worktrees/vollintegration
branch: claude/NEUBAU-VOLLINTEGRATION-2026-07-07

## Why This Plan Is Active (in diesem Worktree)

User-Entscheidung 2026-07-07 (Chat, woertlich): "Gate aufheben, mach parallel
im eigenen Worktree — aber nach der Beendung des Plans und wenn alles fertig
getestet ist und funktioniert muss es automatisch mit dem main zusammengefuegt
und integriert werden, damit ich alles Neue und Gefixte in der App testen kann."

Damit ist das urspruengliche Gate ("erst nach Abschluss+Test des
Audit-Fixplans") explizit aufgehoben. Parallel-Setup:

- Haupt-Worktree (Repo-Root): `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`
  (anderer Agent/Chat) auf `codex/OTK-021-source-consolidation-2026-06-22`.
- Dieser Worktree: NUR `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`
  auf `claude/NEUBAU-VOLLINTEGRATION-2026-07-07` (Basis ed3fa63).

## Verbindlicher Abschluss (User-Auftrag)

Nach Abarbeitung ALLER Tasks + gruenem Regressions-Gate (inkl.
SCHNITT-Garantien: Beat-Sync 100 %, exaktes Audio-Ende):
1. Aktuellen Haupt-Branch (`codex/OTK-021-…`, inkl. Audit-Fixplan-Staende)
   in diesen Branch mergen/rebasen, Konflikte aufloesen, volle Testsuite gruen.
2. Automatischer Merge zurueck in `codex/OTK-021-source-consolidation-2026-06-22`
   + Push — ohne weitere Rueckfrage (explizit autorisiert), damit der User
   alles gemeinsam in der App testet. `fixed` setzt danach der User.

## Parallel-Regeln

- Abhaengigkeits-Reihenfolge: M1 zuerst (T2.2 → T2.1 → T2.3 → T2.4);
  T2.5/M2 (Paket 1)/M3 (Paket 3) sobald deren Audit-Voraussetzungen
  (A0/A2/B1/B2/B4) im Haupt-Branch liegen — regelmaessig Haupt-Branch
  einmergen. Paket-1-Default-AN-Abnahme erst nach A2-Merge (kein Lernen
  auf degradierten Daten).
- GPU-Live-Verifies mit dem Haupt-Worktree zeitlich koordinieren
  (eine GTX 1060); eigene Test-Projektordner unter diesem Worktree.
- Vault-Eintraege immer mit Plan-ID `NEUBAU-VOLLINTEGRATION` kennzeichnen.

## Current Next Task

```text
M1 / T2.2 — `audio.v2_default` im Settings-Dialog (USE-012):
Checkbox "Audio-Analyse V2 als Standard" im SettingsDialog, persistiert via
SettingsStore.set_nested("audio","v2_default", ...). Verify: False ->
klassischer Sequenz-Pfad (_analyze_all_sequential) im Log; True -> V2;
Setting uebersteht App-Neustart.
```
