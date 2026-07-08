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
M2 (Paket 1, T1.1-T1.6) code-complete — Synthese:
`docs/superpowers/synthesis/neubau-vollintegration-m2-done-2026-07-08.md`
(Commits 2222f90, 20255b8, 8d7a538, 3182f43, 94e95a4, 8f405c6).
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

**BEIDE Plaene code-complete und in `codex/OTK-021` zusammengefuehrt
(2026-07-08). NUR NOCH USER-AKTION: Live-Test in der App + `fixed`-Marker.**

**Audit-Fixplan** — alle Release-Tasks code-complete/getestet/gepusht
(`4422afa`): A0–A3, B1–B8. B8 (B-602) live bestaetigt (track2b 138
Segmente). A2 (V2-Analyse mood/genre/sub_genre + Waveform) live bestaetigt.
Option B: Default harte Beat-Cuts, Crossfade experimentell. B9 deferred.
Abschluss: `synthesis/audit-fixplan-abschluss-2026-07-08.md`.

**NEUBAUTEN-VOLLINTEGRATION** — parallel im Worktree abgearbeitet, dann
`codex/OTK-021` (inkl. A2) eingemergt und zurueckgemergt:
- M1 (Paket 2): 16 Slice-1-Module produktiv verdrahtet.
- M2 (Paket 1): Studio-Brain live schaltbar, Brain-V3-Reranker, Steer-
  Overrides, Lernschleife (mem_learned_pattern -> Scorer), RL-v2.
- M3 (Paket 3): DAG-Engine schreibt Scene+VectorDB (DbPersistStage);
  **Motion-Paritaet live auf GTX 1060 bewiesen** (Energy-Diff 0.0000,
  Clip 1+3); Setting-Schalter statt Env-Var.
- Zusaetzlich **B-611** (Export-Crash durch Rundung) gefixt, an 1352 echten
  Eintraegen verifiziert.
- Bewusst offen: VLM-Backend (Stub), DEAD-008-Rest, UI-Perf bei sehr vielen
  Clips (92-min-Mix -> ~1352 Clips, 13s/Klick).

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Höhlenmensch-Modus (German, terse) in der Kommunikation beibehalten.
- GPU-Regel unverändert (GTX 1060 / cuda:0).
- fixed-Marker setzt nur der User.
