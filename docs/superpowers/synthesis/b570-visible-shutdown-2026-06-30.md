# B-570 Visible Shutdown Verifier — 2026-06-30

Status: agent-live-pass-with-limit

Scope:

- Bug: B-570 shutdown with running/cancelled tasks leaving a headless process.
- Verifier: `scripts/diag/verify_b570_shutdown_visible.py`.
- Path exercised: visible Qt window, real `PBWindow.closeEvent`, real `QMessageBox`
  titled `Laufende Tasks`, pywinauto click on `Yes`, cancelled-but-running
  QThread, process-exit check.

Command:

```powershell
$env:CUDA_MODULE_LOADING='LAZY'
$env:PB_REQUIRE_NVENC='1'
$env:KMP_DUPLICATE_LIB_OK='TRUE'
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
& 'C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe' scripts\diag\verify_b570_shutdown_visible.py --timeout-s 60
```

Result:

```json
{
  "ok": true,
  "clicked_dialog": true,
  "clicked_button": "Yes",
  "dialog_title": "PB_studio B570 Visible Shutdown",
  "returncode": 0,
  "alive_after": false
}
```

Relevant stdout tail:

```text
{"event": "thread_started", "thread_running": true}
{"event": "window_shown", "title": "PB_studio B570 Visible Shutdown"}
{"event": "close_event_enter", "thread_running": true}
{"event": "close_event_return", "thread_running": true}
{"event": "event_loop_return", "thread_running": true}
{"event": "waiting_for_hard_exit"}
```

Relevant stderr tail:

```text
closeEvent: Task task_84fbec0e7a7f beendet sich nicht in 3000ms; Hard-Exit nach synchronem Cleanup wird vorgemerkt.
closeEvent: Threads nach Join-Deadline aktiv (task_84fbec0e7a7f); Hard-Exit-Wächter in 1s aktiviert.
```

Focused regression:

```text
tests/test_services/test_b570_shutdown_tasks.py
tests/test_services/test_b570_shutdown_process.py
3 passed in 14.80s
```

Honest limit:

This is stronger than the offscreen child test and covers the previously missing
visible confirmation click. It is still a minimal PBWindow/live-QThread verifier,
not the full original production case with five concurrent analysis pipelines.
No `fixed` marker was set.
