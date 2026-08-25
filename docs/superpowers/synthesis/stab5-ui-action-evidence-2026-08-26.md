# STAB-5 UI-Aktionsbelegabgleich

Datum: 2026-08-26
Status: gap-confirmed
Basis: `b18c448`

## Auftrag

`STAB-5 / UI-Ehrlichkeits-DoD gegen Inventar und vorhandene Testbelege abgleichen`.

## Vorhandene Belege

- 190 Dateien unter `tests/ui/`; 142 Repo-Synthesen.
- Hauptfenster/Tools: Shortcut-, Save-, Task-Dock-, Statusbar- und
  Konsolentests.
- Media/Analyse: Media-Pool-, Pipeline-Progress-, Audio-Retry-, Video-Status-
  und Proxy-Cancel-Tests.
- SCHNITT/Timeline: Controller-Wiring, Action-Gating, Undo, Trim, Lock,
  Thumbnails, Virtualisierung plus GUI-Live-Synthesen.
- Studio Brain: Fenster-/Singleton-/Tooltip-Tests plus STAB-3-Livebelege.
- ChatDock: Quick Commands, Watchdog/Cancel, Registry-Race, Stale Result,
  Main-Thread-Delivery plus aktueller Tool-Livepfad.
- Convert/Deliver: Main-Thread-Delivery, Progress-Range und echter
  Export-Cancel-/Fallback-Livebeleg.
- Stems/Audio: Controller-, Onset-, Workspace-Dispatch- und Waveformtests.
- Setup/Settings/Tooltips: First-Run, Wiederkehr, Thread-Cleanup, B-900-
  Fehlerpfad, Settings-Save sowie statische/dynamische Tooltip-Tests.

## DoD-Abgleich

| STAB-5-Kriterium | Stand |
|---|---|
| Controls inventarisiert | belegt: 182 Controls, 103 UI-Dateien |
| Aktion und Handler/Zustand | aggregiert belegt; 25 Cross-File-Kandidaten verfolgt |
| Erfolg, Fehler/Cancel und Testbeleg je Element | **nicht elementgenau belegt** |
| Kein 100 % bei Fehler | B-900 echter App-Pfad gruen/`fixed` |
| Keine sichtbaren No-Ops | direkte Leerhandler ausgeschlossen; elementgenauer Livebeleg fehlt |
| Fehlende Features kennzeichnen statt neu entwickeln | kein neues Feature in STAB-5 entwickelt |

## Ehrliche Luecke

Vorhandenes Inventar ist nach Bereichen aggregiert. Es enthaelt keine stabile
Zeile pro sichtbarem Control mit Source-Line, Signal, Handler/Worker,
Zustandsaenderung sowie konkretem Test-/Livebeleg. Deshalb kann aus 190
UI-Testdateien nicht ehrlich abgeleitet werden, dass alle 182 Controls den
DoD-Satz "je Element" erfuellen. STAB-5 bleibt `in_progress`.

Keine Tests ausgefuehrt. Diese Task hat ausschliesslich vorhandene Belege
inventarisiert.

## Naechste einzige Task

`STAB-5 / 182 Controls in elementgenaue Evidence-Matrix ueberfuehren`.

Erst danach werden nur echte Restluecken am spaetestmoeglichen Endgate gezielt
getestet.
