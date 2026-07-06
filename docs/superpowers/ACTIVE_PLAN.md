# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-schnitt-clipauswahl-thumbnails-fixplan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-schnitt-clipauswahl-fixplan-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-063-schnitt-clipauswahl-fixplan.md
updated: 2026-07-07

## Why This Plan Is Active

User-Auftrag 2026-07-07 (Chat-Session): Untersuchung des finalen Renders
(`outputs/final-check/exports/output.mp4`) + Session-Logs ergab 6 Defekt-Komplexe
(Clip-Wiederholung, tote Motion-Scores, Caption-Muell, fehlende Thumbnails,
Timeline-Ueberfuellung, zu kleine Clip-Felder). User hat den Fixplan explizit
freigegeben: "ja setzte deinen plan jetzt" + "mach direkt alles … arbeite autonom
alles komplett durch".

Vorheriger aktiver Plan `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
(OTK-021 Verifikations-Phase) ist pausiert, nicht beendet; Rueckkehr nach Abschluss
dieses Fixplans.

## Current Next Task

```text
Schritt 1: Motion-Score-Normalisierung reparieren
(services/video_analysis_service.py::_raft_motion_score — min(1.0, raw/40)
saettigt 41/42 Szenen auf 1.0). Danach Schritte 2-9 sequentiell laut Plan.
User-Vorgaben: Schritt 7 in Variante V3 (nur benoetigte Clips weitergeben,
farbliche Markierung verwendet/unverwendet im Material-Grid, Wahl manuell/auto);
Schritt 8 erst nach Profi-Software-Recherche (B-525).
`fixed`-Marker setzt nur der User nach eigener Live-Sichtung.
```

## Agent Behavior

- Nur dieser Plan; eine Task nach der anderen, Vault-Eintrag pro Sub-Schritt.
- GPU-Regel unveraendert (GTX 1060 / cuda:0 / NVENC; sonst CPU).
- Keine Nicht-Ziele aus Teil D des Plans anfassen (keine Modell-/Library-Swaps,
  keine DB-Migrationen, kein Timeline-Redesign ueber Schritt 8 hinaus).
