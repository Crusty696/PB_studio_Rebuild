# STAB-5 Control #26 — Crashdialog Log-Datei oeffnen

Datum: 2026-08-27
Status: `finding-open:B-906`

## Pfad

Echter `CrashDialog` → sichtbarer/aktiver QPushButton `Log-Datei öffnen` →
echter Mausclick → `_open_log` → existierende Logdatei zum OS-Viewer.

## Ergebnis

- Echter Dialog besitzt genau einen sichtbaren/aktiven Log-Button.
- QTest-Mausclick reicht existierende Logdatei an Windows-Viewer weiter.
- Gezielter Erfolgspfadtest `1 passed in 0.84s`.
- Kein Produktcodeedit in dieser Evidence-Einheit.

## Finding B-906

Fehlen kanonischer und CWD-Logpfad, endet `_open_log` sichtbar still. Fehler von
`os.startfile`/`subprocess.Popen` bleiben ungefangen. Control bleibt offen, bis
B-906 Root Cause und Fehlerfeedback schliesst.
