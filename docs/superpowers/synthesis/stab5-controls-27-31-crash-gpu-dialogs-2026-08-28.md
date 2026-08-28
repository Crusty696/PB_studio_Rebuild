# STAB-5 Controls #27-#31 — CrashDialog-Schliessen + GpuRecoveryDialog (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#27** `CrashDialog btn_close / Schliessen`: genau ein sichtbarer/aktiver
  Button; echter QTest-Mausclick emittiert `accepted` genau einmal, setzt
  `Accepted`-Resultat und versteckt den Dialog.
  Test: `tests/ui/test_stab5_crash_log_open_control.py::test_crash_dialog_close_button_accepts_and_hides`.
- **#28** `GpuRecoveryDialog _btn_recheck / GPU erneut pruefen`: einzig,
  sichtbar, aktiv; Click setzt `choice() == "recheck"` und akzeptiert.
- **#29** `_btn_restart / PB Studio beenden (Reboot)`: Click setzt
  `choice() == "restart"` und akzeptiert; kein automatischer Reboot-Aufruf
  (bewusstes Design, Docstring).
- **#30** `_btn_cpu / Mit CPU starten`: Click setzt
  `choice() == "cpu_fallback"`, setzt `PB_STUDIO_FORCE_CPU=1` und akzeptiert
  (Env-Flag im Test isoliert auf-/abgebaut).
- **#31** `_btn_cancel / Abbrechen`: Click behaelt Default-`choice`
  `"cancel"` und rejected den Dialog.

## Verifikation

- `tests/ui/test_stab5_crash_log_open_control.py` → `4 passed in 0.90s`
  (inkl. B-906-Fehlerpfade und Erfolgspfad #26).
- `tests/ui/test_stab5_gpu_recovery_controls.py` (neu) → `4 passed in 0.87s`.
- Kein Produktcodeedit in dieser Gruppe.

## Grenzen

Echter App-Startpfad mit realem GPU-Stuck-State (Code 47/10) und echter
Crash-Kontext bleiben Live-Endgate. Matrixstand fuer #27-#31:
`target-test-pass-live-pending`.
