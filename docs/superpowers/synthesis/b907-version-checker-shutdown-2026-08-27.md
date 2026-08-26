# B-907 VersionCheckWorker-Shutdown — 2026-08-27

## Root Cause

`VersionCheckWorker.finished -> deleteLater` loeschte das C++-Objekt, waehrend
`PBWindow._version_checker` den ungueltigen Python-Wrapper behielt.
`closeEvent()` rief darauf `isRunning()` auf.

## Fix

`_stop_version_checker()` loest die Referenz vor Zugriff, prueft
`shiboken6.isValid` und stoppt nur einen gueltigen laufenden Worker.

## Verifikation

- `py_compile` fuer Produktdatei und Test: PASS.
- `tests/test_ui/test_b907_version_checker_shutdown.py`: `1 passed in 5.06s`.
- Normaler Worktree-App-Start, responsives MainWindow, spontaner Close,
  kompletter Cleanup, App/Launcher beendet: PASS.
- Kein `RuntimeError`, kein `Internal C++ object`, kein Traceback.

Status: `fixed`.
