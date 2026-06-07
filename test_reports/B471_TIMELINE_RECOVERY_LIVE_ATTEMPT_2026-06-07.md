# B-471 Timeline Recovery Live Attempt - 2026-06-07

Status: code-complete-live-pending

## Scope

Plan: `PB-STUDIO-B471-TIMELINE-USABILITY-RECOVERY-2026-06-07`

User-reported failures:

- Zoom moves A1/V1 lanes upward and makes audio nearly invisible.
- Video timeline items show no useful thumbnails.
- Audio timeline item is only a flat bar.
- Pacing area and tooltips do not explain usable actions.

## Code/Test Result

- Added focused regression tests in `tests/ui/test_b471_timeline_usability_recovery.py`.
- Baseline run against `HEAD` before the UI fixes failed for lane fit, thumbnail width cap, missing waveform overlay, weak pacing tooltip, and weak timeline toolbar tooltip: `5 failed, 2 passed`.
- Implemented narrow UI fixes in:
  - `ui/timeline.py`
  - `ui/workspaces/schnitt/timeline_shell.py`
  - `ui/workspaces/schnitt/tab_pacing_anker.py`
- Added `run_pytest_schnitt.bat` so SCHNITT focused tests use the same `pb-studio` Conda Python as the app instead of relying on `python` being on PATH.

## Verification Run

Commands run:

```text
C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\ui\test_b471_timeline_usability_recovery.py tests\test_ui\test_b471_thumbnail_request_path.py -q
C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe -m py_compile ui\timeline.py ui\workspaces\schnitt\tab_pacing_anker.py ui\workspaces\schnitt\timeline_shell.py tests\ui\test_b471_timeline_usability_recovery.py
C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe -c "from main import PBWindow; print('OK')"
cmd /c run_pytest_schnitt.bat
```

Observed results:

- Baseline detached worktree at `C:\tmp\pb-b471-baseline`: `5 failed, 2 passed`.
- `tests/ui/test_b471_timeline_usability_recovery.py` + thumbnail request path: `10 passed`.
- `run_pytest_schnitt.bat`: `18 passed`.
- Py-compile of affected files passed.
- Import smoke: `OK`; stderr/stdout included GPU readiness warning: `dGPU noch nicht bereit ... PnP-Abfrage hat das Zeitlimit (5 s) ueberschritten.`

## Live App Attempt

App was restarted and SCHNITT opened.

Screenshot:

```text
test_reports/b471_live_after_fix.png
```

Observed blocker:

- App showed `Kein Projekt aktiv.`
- Log showed `get_active_project_id(): Kein aktives Projekt in der DB gefunden`.
- Timeline built with `registered_paths=0 clips=0`.
- Thumbnail request path logged `keine registrierten Thumbnail-Pfade`.

Conclusion:

Real timeline workflow was not verified. No `fixed` claim. Status remains `code-complete-live-pending`.
