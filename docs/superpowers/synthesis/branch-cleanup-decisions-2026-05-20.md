# Branch Cleanup Decisions 2026-05-20

Status: `in_progress`

Basis:
- Aktueller Branch: `feat/video-pipeline-engine-2026-05-19`
- Start-HEAD: `eb801c1`
- B-282-Port-Commit: `b0013cd`

## 1. B-282 Branch

Branch: `codex/bug-task-list-2026-05-07`

Entscheidung:
- Kein Blind-Merge, weil `git merge-tree` einen echten Konflikt in `ui/controllers/media_table.py` gemeldet hat.
- Der fehlende Teil wurde manuell portiert: explizite `Qt.ConnectionType.QueuedConnection` fuer `TaskManager`-Callbacks.

Verifikation:
- `python -m py_compile services/task_manager.py tests/test_services/test_b222_signal_queued_connections.py` mit `pb-studio`-Conda-Python: passed.
- `pytest tests/test_services/test_b222_signal_queued_connections.py tests/ui/test_schnitt_audio_video_combo.py::test_b314_director_combos_select_first_real_project_media tests/ui/test_schnitt_action_gating.py -q`: `13 passed in 4.60s`.

Live-Status:
- Kein sichtbarer User-Klick-Live-Test ausgefuehrt.
- Kein Bug auf `fixed` gesetzt.

## 2. Auto-Merge Workflows

Refs:
- `origin/main`
- `origin/workflow/auto-merge-cleanup`

Entscheidung:
- Nicht in den aktuellen Branch uebernehmen.
- Blockiert bis zu expliziter Governance-Freigabe.

Faktischer Grund:
- `.github/workflows/auto-merge.yml` aktiviert PR-Auto-Merge.
- `.github/workflows/auto-merge-all-prs.yml` kann PRs automatisch mergen und Branches loeschen.
- Das veraendert Repository-Verhalten, nicht nur App-Code.

Status:
- `blocked-by-governance`

## 3. Stale Local Branch Cleanup

Geloescht nach `git branch --contains`-Pruefung:
- `backup/schnitt-redesign-2026-05-11` at `ed9be02`
- `backup/schnitt-redesign-2026-05-11-v2` at `ed9be02`
- `feat/schnitt-redesign-2026-05-09` at `1af205e`

Nicht geloescht:
- `main`
- Remote-Branches
- `sandbox/audio-analysis-v2`
- `sandbox/ux-redesign-2026-05-17`
- `codex/bug-task-list-2026-05-07` wegen separatem Worktree und B-282-Historie

## 4. `feat/audio-analysis-v2`

Entscheidung:
- Nicht loeschen.
- Nicht in den aktuellen Branch mergen.
- In `PLAN_REGISTRY.md` auf `blocked` gesetzt, bis der Branch separat gegen den aktuellen Stand reconciled wurde.

Fakten:
- Branch ist 141 Commits hinter dem aktuellen Branch und 5 Commits voraus.
- Enthaltene Pfade: `_sandbox_meta/*`, `run_sandbox_app.ps1`, `services/audio*`, `services/stem_router.py`, `services/av_pacing_service.py`, `workers/audio_analysis.py`, Audio-Service-Tests.
- `merge-tree` meldete keinen Konflikt, aber das beweist keine fachliche Kompatibilitaet.

Status:
- `blocked-needs-audio-v2-reconciliation`

## 5. `origin/main` Strategy

Entscheidung:
- Aktuellen Branch nicht mit `origin/main` mergen.
- Lokales `main` jetzt nicht aktualisieren.
- `origin/main` bleibt read-only beobachtet, bis D-047 aufgehoben oder ersetzt wird.

Fakten:
- `origin/main` ist 1 Commit vor lokalem `main`.
- Der neue Commit fuegt `.github/workflows/auto-merge.yml` hinzu.
- Kein App-Code-Fix wurde in `origin/main` gefunden.

Status:
- `blocked-by-D-047`

## 6. Live Verification Attempt

Ausgefuehrt mit:
- `PB_PYTHON=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe`
- `tests/gui_harness.py start --force --freeze-probe`
- `tests/gui_harness.py wait-window --title PB_studio --timeout 90`
- `tests/gui_harness.py click-element ...`
- `tests/gui_harness.py screenshot ...`
- `tests/gui_harness.py log-since ...`
- `tests/gui_harness.py kill --grace-sec 20`

Verifizierte sichtbare Schritte:
- App gestartet: Fenster `PB_studio v0.5.0 — Director's Cockpit` gefunden.
- Screenshot erstellt: `tests/qa_artifacts/branch_cleanup_live_start_20260520_161520.png`.
- `Schnitt Workflow` geklickt.
- Screenshot erstellt: `tests/qa_artifacts/branch_cleanup_live_schnitt_20260520_161552.png`.
- `Material und Analyse Workflow`, `Projekt Workflow`, `Export Workflow`, `Brain` geklickt.
- Screenshot erstellt: `tests/qa_artifacts/branch_cleanup_live_nav_20260520_161634.png`.
- Studio Brain Window wurde laut Log geoeffnet.
- App wurde graceful beendet.

Log-Befund fuer aktuelle Session:
- Keine neue `CRITICAL`/Traceback-Zeile im geprueften Logabschnitt nach den Klicks.
- Mehrere `services.perf_watchdog` Slow-Event-Warnungen, u.a. `5070ms | Timer -> QPushButton(?)` beim Brain-Oeffnen.

Nicht verifiziert:
- Kein Audio-Import mit realer Datei.
- Kein Video-Import mit realer Datei.
- Kein Timeline-Aufbau mit echten Medien.
- Kein Auto-Edit-End-to-End.

Status:
- `live-smoke-navigation-passed`
- `full-user-workflow-pending`
