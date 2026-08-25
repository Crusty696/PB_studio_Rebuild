# STAB-5 UI-Aktionsinventar

Datum: 2026-08-26
Commit-Basis: `2e31c4d`
Status: inventory-complete-fix-pending

## Auftrag

`STAB-5 / sichtbare UI-Aktionen inventarisieren und ihren realen
Handler-/Zustandspfad belegen`.

## Scope und Methode

- `main.py` plus 103 Dateien unter `ui/` statisch gelesen.
- Konstruktoren gezaehlt: 124 `QPushButton`, 1 `QToolButton`, 10 `QAction`,
  6 `QShortcut`, 11 `QCheckBox`, 30 `QComboBox`.
- 636 Signal-`connect`-Occurrences inventarisiert; darunter 161 `clicked`,
  12 `triggered`, 10 `toggled`.
- 25 Controls ohne lokale Verbindung in ihrer Erstellungsdatei repo-weit
  verfolgt: alle besitzen externe Controllerbindung oder QMenu-Wirkung.
- Verbundene Handler auf reine Leerkoerper geprueft: kein `pass`,
  `return None`, Ellipsis oder `lambda: None` als direktes Signalziel.
- Menue-Actions gegen direkte Callbacks, `triggered.connect`,
  `menu.exec()`-Rueckgabevergleich oder explizit deaktivierte Infoeintraege
  abgeglichen.

## Matrix

| Bereich | Aktion -> Handler/Zustand | Ergebnis |
|---|---|---|
| Hauptfenster/Tools | Kontext, Tasks, Konsole, Chat, Projekte, Import, Brain, Settings | verdrahtet |
| Shortcuts | F1/Ctrl+?, Ctrl+B, Undo, Redo, Save | verdrahtet |
| Media/Analyse | Auswahl, Timeline-Add, Status, Retry, Video-/Audio-Pipeline | verdrahtet; pending/running/error/degraded/done getrennt |
| SCHNITT | Generate, Auto-Edit, Regenerate, Anker, Preview, Timeline-Kontext | verdrahtet |
| Studio Brain | Boost/Exclude, Pins, Filter, Run, Story Map, Lernen | verdrahtet |
| Convert/Deliver | Standardisieren, Effekte, Preview, Export, Preset, Cancel/Fehler | verdrahtet; Exportwarnung verhindert stillen Vollerfolg |
| Stems | Play/Stop, Mute, Solo, Volume | verdrahtet; Solo ueber `StemWorkspace._on_solo_toggled` |
| ChatDock | Enter/Senden, Quick Commands, Agentworker, Watchdog, Fehler | verdrahtet; fehlender Agent sichtbar |
| Setup-Wizard | Modellschritt-Fortschritt und Ergebnis | **B-900: 100 Prozent auch bei Fehler** |

## Finding

### B-900 high — Setup-Wizard 100 Prozent bei Fehler

`SetupWizard._on_step_done` setzt Modellbalken immer auf 100 und berechnet
Gesamtprozent aus beendeten Versuchen, auch bei `ok=False`. Fehlerfarbe und
-text sind korrekt, Prozentsemantik nicht. Vault:
`wiki/bugs/B-900-setup-wizard-100-prozent-bei-fehler.md`.

## Grenzen

- Statische Verdrahtung ist kein Livebeweis fuer jeden UI-Pfad.
- Kein breiter UI-Test und kein App-Neustart in dieser Inventar-Task.
- Gemaess Uservorgabe folgt nur der minimal betroffene B-900-Test am spaeten
  Fix-Endgate.

## Naechste einzige Task

`STAB-5 / B-900 Setup-Wizard darf Fehler nicht als 100 Prozent darstellen`.
