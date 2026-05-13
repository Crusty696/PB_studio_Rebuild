---
title: SCHNITT Usability + Wiring Rebuild Design
date: 2026-05-13
status: approved-for-planning
scope: schnitt workspace wiring timeline audio stems usability tooltips live verify
related: ["B-310", "B-309", "2026-05-09-schnitt-workspace-redesign"]
vault_anchor: projects/pb-studio/wiki/bugs/B-310-schnitt-workspace-unusable-half-wired-ux.md
---

# SCHNITT Usability + Wiring Rebuild Design

## Ziel

SCHNITT wird von einer teils verdrahteten Oberflaeche zu einem klaren,
bedienbaren Arbeitsbereich. Der User muss beim ersten Blick verstehen:

- welches Projekt aktiv ist,
- welches Audio die Schnittbasis liefert,
- welche Videos als Materialpool verfuegbar sind,
- was die Timeline zeigt,
- wie Zoom/Pan/Play/Lock funktionieren,
- welche Controls echte Aktionen ausloesen,
- welche Daten noch fehlen.

Der Umbau ist **Wiring-first**. UI-Polish ohne funktionierende Datenweitergabe
ist verboten. Wenn ein bestehendes SCHNITT-Widget nur Skeleton ist oder mehr
Adapter-Risiko erzeugt als Nutzen, wird es ersetzt statt weiter geflickt.

## Nicht verhandelbare Befunde

B-310 zeigt echte strukturelle Fehler:

1. `SchnittTabAudio` erzeugt eigene `StemWorkspace`, aber Produktiv-Wiring
   zeigt weiter auf `_stems_ws.stem_widget`.
2. `SchnittTabAudio` hat Render-Methoden fuer Waveform/Beatgrid/Struktur/LUFS/Key,
   aber keine robuste Produktionsleitung bei aktivem Audio-Wechsel.
3. SCHNITT nutzt weiterhin globale `self.window.*` Promotions und alte
   `EditWorkspaceController`-Pfade. Das macht Datenfluss schwer nachvollziehbar.
4. Timeline hat Funktionen, aber keine klare Bedienoberflaeche fuer Zoom/Pan/Fit,
   keine ausreichende visuelle Legende und zu wenig erklaerende Statusmeldungen.

## Architektur

Neue Schnitt-Schicht:

```text
SchnittWorkspace
  -> SchnittCoordinator
      -> SchnittDataContext
      -> SchnittAudioBinder
      -> SchnittTimelineBinder
      -> SchnittActionBinder
```

### `SchnittDataContext`

Ein kleines, testbares Objekt haelt den aktuellen Arbeitskontext:

- `project_id`
- `project_path`
- `audio_id`
- `video_ids`
- `timeline_entry_count`
- `has_stems`
- `has_waveform`
- `has_beatgrid`
- `has_video_analysis`

Es wird aus DB und sichtbarer Medienauswahl aufgebaut. Kein SCHNITT-Subtab
soll selbst erraten, welches Projekt oder Audio aktiv ist.

### `SchnittCoordinator`

Ein Coordinator sitzt zwischen `PBWindow`, `SchnittWorkspace`, alten Services
und neuen Bindern. Er ist der einzige Ort, der bei Projektwechsel, Audio-Wechsel,
Video-Import, Analyse-Fertigstellung oder SCHNITT-Tab-Wechsel den gesamten
SCHNITT-Zustand refreshed.

Verboten nach diesem Plan:

- neue direkte `self.window.<schnitt-widget>` Zugriffe aus fremden Controllern,
- neue SCHNITT-Logik in `EditWorkspaceController`,
- UI-Controls, die sichtbar aktiv sind, aber keinen echten Slot haben.

### `SchnittAudioBinder`

Bindet aktives Audio an:

- Header-Audio-Combo,
- Audio-Subtab-Waveform,
- Beatgrid-Linien,
- Strukturmarker,
- LUFS-Anzeige,
- Tonart-Anzeige,
- Stems-Mixer im SCHNITT-Audio-Tab,
- StemPlayer-Signale.

Die alte Stems-Seite darf weiter existieren, aber SCHNITT muss eigene aktive
Stems korrekt sehen und bedienen.

### `SchnittTimelineBinder`

Fuegt eine klare Timeline-Shell um `InteractiveTimeline`:

- Zoom-Leiste mit Buttons: `-`, `Fit`, `100%`, `+`,
- sichtbarer Zoom-Prozentwert,
- Pan-Hinweis,
- Track-Legende fuer Audio, Video, Cuts, Locks, Anker,
- Statuszeile: Clipanzahl, Timeline-Dauer, Cutanzahl, Lockanzahl,
- Empty/Disabled-Hinweise, wenn Daten fehlen.

`InteractiveTimeline` bleibt Kernkomponente, weil dort Undo, Drag, Lock,
DB-Load, Beatgrid und Keyboard-Shortcuts bereits real existieren. Neu gebaut
wird die bedienbare Shell und der Datenbinder, nicht die komplette
QGraphicsView-Engine.

### `SchnittActionBinder`

Verdrahtet Aktionen an klare Preconditions:

- `Timeline generieren` braucht aktives Projekt + Audio + mindestens ein Video.
- `Auto-Edit` braucht aktives Projekt + analysiertes Audio/Beatgrid + Videos.
- `Re-Generate` braucht vorhandene Timeline.
- Anchor-Aktionen brauchen selektierten Clip oder gewaehlte Szene.
- RL-Feedback braucht vorhandenen letzten Auto-Edit-Run.

Wenn Preconditions fehlen, Button disabled + Tooltip mit konkretem Grund.
Kein silent return.

## UX-Regeln

1. Jeder aktive Button hat Tooltip, AccessibleName und sichtbaren Effekt.
2. Jeder disabled Button hat Tooltip mit Grund.
3. SCHNITT zeigt oben eine Statusleiste:
   `Projekt | Audio | Videos | Analyse | Timeline`.
4. Jede Subtab-Ueberschrift enthaelt einen kurzen Status:
   `Audio: Stems bereit`, `Timeline: 47 Clips`, `Pacing: 4 Beat`.
5. Timeline-Interaktion ist explizit:
   - Wheel zoomt nur mit `Ctrl` oder wenn Zoom-Modus aktiv ist.
   - normale Wheel-Bewegung scrollt horizontal/vertikal.
   - Buttons bieten Alternative zu Wheel.
6. Skeleton-Flaechen sind verboten. Fehlende Daten werden als Empty-State mit
   naechster Aktion gezeigt.

## Neubau-Entscheidung

Direkt neu machen:

- `SchnittCoordinator`
- `SchnittDataContext`
- `SchnittAudioBinder`
- `SchnittTimelineBinder`
- `SchnittActionBinder`
- Timeline-Shell/Toolbar um bestehende `InteractiveTimeline`

Behalten:

- `InteractiveTimeline` als Grafik-/Undo-Kern
- `AutoEditWorker`
- `services.timeline_service`
- `services.pacing_service`
- `StemWorkspace` Widget, aber neu in SCHNITT verdrahtet
- DB-Modelle und bestehende Snapshot-/Notes-Services

Sunset:

- SCHNITT-relevante neue Logik in `EditWorkspaceController`.
- Globale Promotionen bleiben nur fuer Rueckwaertskompatibilitaet bis alle
  Controller auf Coordinator laufen. Danach werden sie entfernt.

## Live-Akzeptanz

Der alte 16-Schritte-Live-Verify wird ersetzt/erweitert:

1. Neues Projekt oeffnen/anlegen.
2. Audio importieren/analyse bestaetigen.
3. Stems separieren.
4. Videos importieren/analyse bestaetigen.
5. SCHNITT oeffnen.
6. Statusleiste zeigt Projekt/Audio/Videos korrekt.
7. Audio-Subtab zeigt Waveform, Beatgrid, Struktur, LUFS/Key und Stems.
8. Stem-Mute/Solo/Volume im SCHNITT-Subtab steuert echten StemPlayer.
9. Timeline-Subtab zeigt klare Spuren/Legende/Status.
10. Zoom-Buttons, Fit und 100% funktionieren sichtbar.
11. Wheel-Verhalten verstellt nicht versehentlich Timeline/Combos.
12. Clip-Auswahl fuellt Inspector.
13. Lock-Icon togglet sichtbar und persistiert.
14. Auto-Edit erzeugt Timeline oder zeigt konkreten fehlenden Grund.
15. Re-Generate respektiert Locks.
16. Notes speichern und laden.
17. Keine sichtbaren Dummy-Controls ohne Funktion.
18. Screenshots + Logs liegen im Vault.

Status `fixed` fuer B-310 gibt es erst nach diesem Live-Lauf.
