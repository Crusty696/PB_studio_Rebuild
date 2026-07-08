# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-AUDIT-FIXPLAN-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-audit-fixplan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-audit-fixplan-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-064-audit-fixplan-und-vollintegration.md
updated: 2026-07-08

## Why This Plan Is Active

Der SCHNITT-Fixplan wurde am 2026-07-08 vom User erfolgreich live-verifiziert und auf `fixed` gesetzt.
Nun wird plangemäß auf den Audit-Fixplan `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07` umgeschaltet, um offene Fehler, Lücken und toten Code zu beheben. Alle Blocker (R3-Gate) sind durch die SCHNITT-Freigabe aufgehoben.

## Current Next Task

Wir beginnen mit der Ausführung des Audit-Fixplans gemäß der definierten Reihenfolge:
1. **A0: Smoke-Test des E2E-Render-Pfads (repro-gated)**
   - Testdurchlauf mit Testset: Video-Ordner `Solo_Natur`, Audio `Crusty Progressive Psy Set2.mp3` importieren -> Analyse -> Auto-Edit -> Export.
   - Ergebnis-Video und Logs sichern, um Lauffähigkeit zu belegen.
2. **A3: DB-010 Migration (präventiv)**
   - Nachrüst-Migration für `beatgrids.stem_weighted_energy` in `database/migrations.py` implementieren.
3. **B1 bis B4, B7 (Stille Degradierung robust machen)**
4. **A1 (Crossfades + UI-Schalter)** und **A2 (V2-Default komplett)**
5. **B5, B6**

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Höhlenmensch-Modus (German, terse) in der Kommunikation beibehalten.
- GPU-Regel unverändert (GTX 1060 / cuda:0).
- fixed-Marker setzt nur der User.
