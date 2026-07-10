# Timeline-/Grid-Virtualisierung — Plan (2026-07-10)

plan_id: PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10
status: approved-for-planning
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-066-timeline-virtualisierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-timeline-virtualisierung-2026-07-10.md

## Problem (profil-bewiesen, 2026-07-10)

Nach den Freeze-Fixes vom 2026-07-10 (Recent-Open async `9ddeec6`,
Export-Summary async `9ddeec6`, Projekt-ID-Cache + Gates-Worker `7e0f96e`)
sind ALLE DB-Blocker aus dem Klick-Pfad verschwunden (freeze_stacks-Profil,
Runde 3). Verbleibend: **20–34 s Main-Thread-Freeze beim ersten
MATERIAL-/SCHNITT-Klick nach Projekt-Open** (test33: 1428 Timeline-Cuts,
375 Videos). Der Watchdog-Stack endet an
`workspace_stack.setCurrentIndex(...)` — die Zeit steckt im Qt-C++
Show/Layout/Polish der vollmaterialisierten Widgets:

- InteractiveTimeline: 1428 Clip-Items (Rect+Text+Thumb+Lock) + Cut-Lines
  + Beat-Marker als echte QGraphicsItems in der Scene.
- MediaPoolGrid: 375 VideoCards (Widgets) im Grid.

Vorstufen existieren bereits: lazy Text-Items (`7868107`), Batch-Build 2000
(`83bfa3f`), Grid-lazy-Rebuild bei Unsichtbarkeit (jovial `ddd2293`) — sie
verschieben den Aufbau, virtualisieren ihn aber nicht.

User-Beschluss 2026-07-09 00:25: Virtualisierung als eigener Task. Dieser
Plan loest das ein.

## Ziel / Abnahme

- Erster Workspace-Klick nach Projekt-Open (1428 Cuts / 375 Videos):
  **UI reagiert < 2 s** (Klick-zu-Paint), Inhalt darf danach progressiv
  erscheinen.
- `PB_STUDIO_FREEZE_PROBE=1`-Lauf ueber 3 Wechsel-Zyklen: **kein
  Watchdog-Dump > 2 s**.
- Keine Funktionsregression: Selection, Drag&Drop, Lock, Undo, Zoom,
  Cutliste-Sync, Thumbnails (145 Timeline-Tests + neue Guards gruen).

## Tasks

### M0 — Messbasis (klein)
- [ ] `PB_TIMELINE_PERF`-Messpunkte um `setCurrentIndex`-Show (Scene- vs
      Grid-Anteil in ms), damit jeder M-Schritt belegbar ist.
- [ ] Repro-Harness: `self_test_freeze.py`-Ablauf (Open → Zyklen → Profil)
      als wiederholbares Skript in `scripts/diag/` versionieren.

### M1 — Timeline-Viewport-Virtualisierung (Kern)
- [ ] Clip-Datensaetze von Item-Objekten trennen: leichte Records fuer alle
      1428 Cuts, echte `TimelineClipItem`s NUR fuer Viewport ± Puffer
      (~2 Bildschirmbreiten).
- [ ] Materialisieren/Entmaterialisieren bei Scroll/Zoom (Handler existiert:
      `_request_visible_thumbnails`-Polling als Anker nutzen).
- [ ] Cut-Lines/Beat-Marker viewport-lazy (LOD-Ansatz aus BeatGridItem
      uebernehmen).
- [ ] Selection/Undo/Lock arbeiten auf Records; Item-Zustand wird beim
      Materialisieren angewandt.

### M2 — Show-Entkopplung (Klick reagiert sofort)
- [ ] Beim Workspace-Wechsel: Stack sofort umschalten, Scene-/Grid-Fuellung
      via QTimer(0)-Batches NACH dem ersten Paint (progressiv sichtbar).

### M3 — Grid-Virtualisierung
- [ ] MediaPoolGrid: nur sichtbare Cards bauen (Scroll-Viewport), Rest als
      Platzhalter-Records; bestehendes `_load_next_chunk`-Chunking auf
      Viewport-Steuerung umstellen (kein Vollbuild bei showEvent).

### M4 — Verify (hart)
- [ ] Profil-Lauf (M0-Harness) auf test33: Abnahme-Kriterien oben.
- [ ] Volle Timeline-/Grid-Testsuite gruen; neue Guards fuer
      Virtualisierungs-Invarianten (Item-Count <= sichtbar+Puffer).
- [ ] Live-GUI-Check (pb-gui-tester) + User-Sichtung → `fixed` setzt User.

## Risiken

- Drag&Drop/Rubberband ueber nicht-materialisierte Bereiche (Records muessen
  Treffer liefern).
- Undo-Stack referenziert Items → auf entry_ids umstellen, wo noetig.
- Thumbnail-Pipeline (B-605-Fix `4254d5c`) muss mit Entmaterialisieren
  zusammenspielen (Cache `_thumb_pixmaps` bleibt die Quelle).
- 145 bestehende Timeline-Tests erwarten teils volle `clip_items`-Listen →
  Tests bewusst nachziehen, Invarianten erhalten.

## Nicht-Ziele

- Kein Redesign der Timeline-Optik (Layout steht seit 2026-07-10).
- Keine DB-Schema-Aenderungen.
