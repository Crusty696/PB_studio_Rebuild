# B-906 — Crashdialog-Log-Öffnen meldet Fehler sichtbar (2026-08-28)

status: code-fix-pending-live-verification

## Root Cause

`CrashDialog._open_log()` war `@staticmethod` ohne Fehlerpfade: fehlten beide
Logpfade (`<repo>/logs/pb_studio.log` und CWD-relativ `logs/pb_studio.log`),
endete der Handler still; `os.startfile`/`subprocess.Popen`-Fehler liefen
ungefangen in den bereits laufenden Crash-Kontext.

## Fix

`ui/dialogs/crash_dialog.py`: `_open_log` ist Instanzmethode; fehlende Datei
zeigt `QMessageBox.warning` mit beiden geprüften Pfaden; `OSError` beim
Öffnen zeigt Pfad + Fehlergrund sichtbar. Erfolgspfad unverändert
(win32 `os.startfile`, darwin `open`, sonst `xdg-open`).

## Verifikation

- RED zuerst: 2 neue Tests failten am alten Code
  (`2 failed, 1 passed, 1 error` — Error war die ungefangene OSError).
- GREEN: `tests/ui/test_stab5_crash_log_open_control.py` → `3 passed in 0.80s`
  (Erfolgspfad-Regression #26 weiter grün).
- `py_compile` PASS.

## Grenzen

Echter Crash-Dialog-Livepfad in laufender App bleibt offen (spätes Endgate).
`fixed` bleibt Userrecht.
