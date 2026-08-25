# B-900 Setup-Wizard Fortschrittswahrheit

Datum: 2026-08-26
Status: fixed
Basis: `e42f45f`

## Root Cause

`_completed` zaehlte beendete Versuche, wurde aber als Erfolgsprozent benutzt.
Jede Modellzeile erhielt ausserdem bedingungslos 100 Prozent; `ok` aenderte
nur Farbe und Text.

## Codefix

- `_completed` bleibt Lifecyclezaehler fuer beendete Versuche.
- `_succeeded` zaehlt ausschliesslich erfolgreiche Modellschritte.
- Gesamtbalken zeigt `_succeeded / _total`.
- Erfolgreiche Modellzeile endet bei 100.
- Fehlgeschlagene Modellzeile behaelt ihren Arbeitsfortschritt, maximal 99,
  und zeigt weiter roten Fehlertext.

## Minimal-Endgate

- `python -m py_compile ui/dialogs/setup_wizard.py`: Exit 0.
- `python -m pytest tests/ui/test_b900_setup_wizard_progress_truth.py -q`:
  `1 passed in 0.88s`.
- Kein breiter Testlauf.

## App-Live-Verifikation

`main._maybe_run_setup_wizard()` lief im Projektinterpreter mit isolierten
QSettings, echtem Modal-Dialog, echtem QThread und real verweigertem
Ollama-Verbindungsaufbau auf `127.0.0.1:1`. Ergebnis: Modellbalken 0,
Gesamtbalken 0, roter Fehlertext, Finish-Seite meldet fehlgeschlagene
Downloads, Exit 0. Kein Modell wurde geladen oder heruntergeladen.

## Naechste einzige Task

`STAB-5 / UI-Ehrlichkeits-DoD gegen Inventar und vorhandene Testbelege abgleichen`.
