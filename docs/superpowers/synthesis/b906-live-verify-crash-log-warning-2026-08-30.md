# B-906 Live-Prüfung — sichtbare Warnung bei fehlender Log-Datei (2026-08-30)

status: agent-live-verified-await-user-marker
bug: B-906
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
verifier: Claude (agentseitig, kein User-Marker)

## Ziel

B-906 war `code-fix-pending-live-verification`: `_open_log` im CrashDialog
endete bei fehlender Log-Datei still, und OS-Fehler beim Öffnen blieben
ungefangen. Der Fix macht beides sichtbar. Belegt war das bisher nur durch
Offscreen-Tests (`3 passed in 0.80s`).

## Aufbau und seine Grenze

Der Fehlerpfad lässt sich in der laufenden App nicht auslösen, ohne die echte
Log-Datei zu löschen — das wäre ein Eingriff in laufende Diagnosedaten. Statt
dessen lief ein eigener echter Prozess mit sichtbarem Fenster
(`scratchpad/b906_live_dialog.py`, conda-Python `pb-studio`):

- echter `ui.dialogs.crash_dialog.CrashDialog` mit echter, im Skript
  ausgelöster `RuntimeError`-Exception,
- beide vom Produktcode geprüften Pfade zeigen ins Leere: `_LOG_PATH` auf ein
  nicht existierendes Verzeichnis umgebogen, Prozess-CWD auf ein leeres
  Temp-Verzeichnis gesetzt (damit auch der Fallback `logs/pb_studio.log`
  fehlschlägt),
- Bedienung von außen per UIA-Klick über `tests/gui_harness.py`.

Ehrliche Einordnung: Prozess, Fenster, Button, Klick, Dialog und
Fehlerbehandlung sind echt. Künstlich ist ausschließlich die Abwesenheit der
Log-Datei — anders ist dieser Zweig ohne Datenverlust nicht erreichbar. Der
Weg über einen echten App-Absturz wurde nicht gegangen: einen Crash zu
provozieren war nicht beauftragt.

## Ablauf und Ergebnis

Der Dialog erschien mit Titel, Fehlerzeile
`RuntimeError: B-906 Live-Pruefung: kuenstlich erzeugte Beispiel-Exception`,
Stacktrace-Feld und genau zwei Buttons: `Log-Datei öffnen` und `Schliessen`,
beide sichtbar und aktiv.

Nach dem Klick auf `Log-Datei öffnen` erschien ein zusätzliches Fenster
`Log-Datei nicht gefunden` mit dem Text:

```
Keine Log-Datei gefunden. Geprüfte Pfade:
C:\Users\DAVID_~1\AppData\Local\Temp\b906_live_2uj86hni\definitiv_nicht_vorhanden\pb_studio.log
logs\pb_studio.log
```

Damit ist belegt: der Button endet nicht mehr still, und die Meldung nennt
beide geprüften Pfade — genau der Vertrag des Fixes. `OK` schloss die Warnung,
`Schliessen` den CrashDialog; danach war kein Fenster mehr offen und der
Prozess endete mit Code 0.

## Nicht abgedeckt

- Der Erfolgspfad (vorhandene Log-Datei → `os.startfile`) wurde bewusst nicht
  live geklickt, weil das auf dem Desktop des Users einen Editor mit der
  4,6-MB-Logdatei geöffnet hätte. Er ist durch den bestehenden Test für
  Control #26 abgedeckt.
- Der `OSError`-Zweig (Datei vorhanden, Öffnen scheitert) wurde nicht live
  provoziert.
- Der Weg über einen echten unbehandelten App-Absturz bleibt offen.

`fixed` setzt ausschließlich der User.

## Belege

- Screenshot: `tests/qa_artifacts/b906-live-warning_20260830_195701.png`
- Skript: `scratchpad/b906_live_dialog.py` (außerhalb des Repos)
- Produktcode: `ui/dialogs/crash_dialog.py:158-172`
