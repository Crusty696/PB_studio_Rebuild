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

```text
M3 / Paket 3 — DAG-Video-Engine vollstaendig integrieren
(USE-003 / PIPE-018 / DEAD-008):
1. PIPE-018-Luecken schliessen: Ergebnis-Paritaet der Engine-Pipeline zum
   Monolith (VectorDB-Persistenz, Scene.energy, Cross-Cutting-Module) —
   erst Ist-Stand beider Pfade auditieren (services/video_pipeline/ vs.
   services/video_analysis_service.py::run_full_pipeline).
2. Paritaets-Nachweis mit echten Daten (gleiches Video beide Pfade,
   Diff der persistierten Ergebnisse).
3. Setting-Schalter statt Env-Var PB_ENABLE_VIDEO_PIPELINE_ENGINE
   (Default AUS bis Paritaet bewiesen).
Danach: A2-Nachmerge, volle Testsuite inkl. SCHNITT-Garantien,
automatischer Merge zurueck in codex/OTK-021-... + Push (User-Auftrag).
```
