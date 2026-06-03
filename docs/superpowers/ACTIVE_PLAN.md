# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
next_allowed_task: B-463 Option-A code-complete (TDD green); run default gate + GUI live-verify, then user `fixed` confirmation. B-462-A also awaits user `fixed`. Open: B-464..B-468.
updated: 2026-06-03

## Meaning

Der User hat am 2026-05-31 nach dem Vollprojekt-Audit einen Fixplan ausgewaehlt.

Aktiver Plan:

```text
PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
```

Quell-Audit:

```text
PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31
```

## Agent Behavior

- Nur `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` bearbeiten.
- Registry-/Lifecycle-Status aktuell: code-complete-live-pending.
- User hat Implementierung am 2026-05-31 im Chat freigegeben.
- Task-Reihenfolge aus dem Fixplan strikt einhalten.
- `verified` / `fixed` nur nach realem App-Workflow plus Log-/UI-Beleg.

## Current Status

- Fixplan erstellt aus FPA-001..FPA-010.
- Repo-Plan: `docs/superpowers/plans/2026-05-31-full-project-audit-fixplan.md`.
- Vault-Mirror: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-full-project-audit-fixplan-2026-05-31.md`.
- Decision: `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-055-full-project-audit-fixplan.md`.
- Task 0 Governance And Baseline abgeschlossen: User-Freigabe dokumentiert, Registry/Plan auf `approved-for-implementation` gesetzt.
- Task 1 Honest Test Gate Policy hat CI-/Policy-Gate hinzugefuegt und Policy-Test gruen gemacht.
- User hat am 2026-06-01 entschieden: B-441 aufnehmen und weitermachen.
- B-441 ist als Task 1a in den Fixplan aufgenommen.
- B-441 targeted Tests gruen; Default Gate kam weiter.
- B-442 Governance-Pfad-Fix targeted Test gruen; Default Gate kam weiter.
- B-443 targeted Tests gruen; Default Gate kam weiter.
- B-444 targeted Tests gruen; Default Gate kam weiter.
- B-445 targeted Tests gruen; Default Gate kam weiter.
- B-446 targeted Test gruen; Default Gate crasht nicht mehr bei Pre-Cache.
- B-447 targeted Test gruen; Default Gate kam weiter.
- B-448 targeted Tests gruen; direkter Smoke zeigt `learning_session_under_2s=true`.
- B-449 targeted Tests gruen; Default Gate crasht nicht mehr bei Grid und kam weiter.
- B-450 targeted Test gruen; Default Gate kam weiter.
- B-451 targeted Test gruen; Default Gate kam weiter.
- B-452 targeted Test und Modul gruen; Default Gate erreicht B-452 nicht, weil es vorher nativ crasht.
- B-453 targeted Tests gruen; Default Gate crasht nicht mehr bei Grid und kam weiter.
- B-454 targeted Tests gruen; Default Gate kam weiter.
- B-455 targeted Tests gruen; Default Gate kam weiter.
- B-456 targeted Tests gruen; Default Gate gruen.
- Default pytest gate Ergebnis: `2315 passed, 37 skipped, 6 deselected, 62 warnings in 810.22s`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-441-default-gate-structure-enrichment-zero-scenes.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-442-plan-registry-missing-bug-hunt-repo-path.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-443-default-gate-pacing-cut-points-source-not-beat.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-444-default-gate-grid-stability-access-violation.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-445-default-gate-pacing-scoring-latency-regression.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-446-default-gate-pre-cache-headless-crash.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-447-default-gate-b433-power-status-regression.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-448-default-gate-brain-v3-performance-profile-learning-timeout.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-449-default-gate-grid-stability-crash-recurrence.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-450-default-gate-brain-wiring-b197-pbwindow-mock.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-451-default-gate-stem-separator-fp16-cpu-clamp.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-452-default-gate-corrupt-video-pipeline-missing-clip-message.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-453-default-gate-grid-stability-native-crash-after-b452.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-454-default-gate-video-pipeline-metadata-snapshot-fake-session.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-455-default-gate-schnitt-workspace-switch-refresh-missing.md`.
- Bugfile: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-456-default-gate-thumb-apply-helper-removed.md`.
- Task 2 Runtime Manifest Drift Audit/Fix abgeschlossen: active env Python 3.10.20 + torch 1.12.1+cu113 passt zu `requirements-py310-cu113.txt`; bare `python` ist Conda base Python 3.13.12 + torch 2.6.0+cu124 und darf nicht als App-Runtime verwendet werden.
- Task-2-Synthese: `docs/superpowers/synthesis/runtime-manifest-drift-2026-05-31.md`.
- Task 3 FFmpeg Resolver Unification abgeschlossen: decoder/proxy_generator/stream_hasher nutzen `services.startup_checks` Resolver statt PATH-only `shutil.which`; targeted primitive tests gruen.
- Task 4 DB Project Switch And Soft-Delete Safety abgeschlossen als Coverage/Verification: neue Guard-/Visibility-Tests gruen; kein App-Code-Fix erforderlich. `pytest tests/test_db_deep.py -v` bleibt wegen `sys.exit` im Standalone-Script ein pytest-Runner-Problem; direkte Script-Ausfuehrung ergibt 78 PASS / 0 FAIL.
- Task 5 QThread Lifecycle Contract abgeschlossen als Coverage/Verification: neue finished/error/cancel Lifecycle-Tests und bestehende Dispatcher/TaskManager-Tests gruen; kein App-Code-Fix erforderlich.
- Task 6 Deterministic LLM/Action Boundary Gate abgeschlossen: destruktive Registry-Actions brauchen `confirm=True`; malformed JSON liefert strukturierten Error ohne Side Effect; targeted action tests gruen.
- Task 7 Mutating Surface Guard Tests abgeschlossen: pycache cleanup prueft repo scope; failed Save-As cleanup verweigert source/parent/root; VectorDB delete und Snapshot-Restore scoped; targeted tests gruen.
- Task 8 GPU Serialization Verification Gate abgeschlossen: Lock-Contract-Test hinzugefuegt; targeted GPU contract/model tests gruen; live_gpu Pipeline-E2E gruen; kein manueller App-Workflow.
- Task 9 Boot Path Guardrails abgeschlossen: DB-Bootstrap loggt Critical und beendet sauber bei DB-Fehler; startup checks laufen ohne QApplication; CUDA-unavailable bleibt degradierter Status; Boot-Live-Fenster und Startup-completed-Log belegt.
- Task 10 Final Verification Matrix erstellt: `docs/superpowers/synthesis/full-audit-fixplan-verification-2026-05-31.md`.
- Naechster Schritt: Handoff nach Matrix-Commit; danach User-Live-Entscheidung. Kein `fixed`-Status geschrieben.
- 2026-06-03 Live-Verify (project-audit-team): alle 10 FPA-Funktionen real getestet. 5 green (F1/F2/F3/F4/F8), 3 yellow (F5/F7/F9), 1 red (F6 GUI-Hard-Delete), 1 n/a (F10). Default gate rerun green (2351 passed). Matrix-Live-Sektion committed (1b93a18).
- 7 neue Bug-Files B-462..B-468 (open, kein Fix). B-462 (critical) = GUI-Hard-Delete statt Soft-Delete.
- User-Entscheidung 2026-06-03: B-462 gestuft fixen, A (Soft-Delete) jetzt, C (Two-Tier/Purge) als Folge. Decision D-056.
- Task 11 (B-462-A) + Task 12 (B-462-C) in Fixplan aufgenommen.
- 2026-06-03 Task 11 (B-462-A) implementiert (TDD, D-056 Option 2): `ingest_service.py` delete_selected_media + delete_all_media setzen `deleted_at` statt physisch loeschen; Analyse-Children behalten, Beziehungs-/Timeline-Children entfernt, VectorDB-Embeddings entfernt (B-139/B-350 rollback erhalten). 66 targeted Tests gruen, Default-Gate `2353 passed` (keine Regression), GUI-Tester-Live gruen (Clip id=2: Row bleibt, deleted_at gesetzt, Grid versteckt, Scenes bleiben, Timeline geleert). `status: fixed` nur User.
- Task 12 (B-462-C purge) bleibt geplant, wartet auf User-Freigabe.
- 2026-06-03 B-463 (moondream2 Chat-Crash) untersucht: Revision-Pin loest es NICHT (alle moondream2-Revisionen brauchen torchvision.transforms.v2; env torch 1.12.1+cu113/torchvision 0.13.1 hat das nicht; torch-2.x-Upgrade per GPU-Hartregel verboten). Pin-Versuch reverted, worktree clean. User-Richtung: Option A = VisionAgent/VisionAnalysisService.analyze() auf existierenden Ollama-chat_vision-Pfad umstellen statt HF-moondream2. Mittlerer Service-Umbau. 2026-06-03 IMPLEMENTIERT (User-Freigabe, TDD): zwei Edits — (1) `agents/vision_agent.py` `model_id=None` (verhindert den eigentlichen Crash-Pfad `orchestrator_agent.py:845 ensure_loaded(...,"vision")` HF-Preload VOR process()), (2) `services/vision_analysis_service_moondream.py` `analyze()` auf Ollama `chat_vision` (cv2-Frames bleiben, ModelManager/torch raus, graceful degrade). Neuer Test `tests/test_services/test_vision_analysis_ollama.py` (5 Tests gruen); `test_deep_functional.py:1350` -> model_id None. Regression `-k "orchestrat or vision or model_manager"` 99 passed/0 fail. Default-Gate gruen (2362 passed/0 fail), Commit `1a77db2`. Service-Live gruen (echtes Video -> echte Ollama-moondream-Caption). GUI-Live-Verify (pb-gui-tester) gruen: Orchestrator-Crash weg (0 neue Crash-Marker, kein torchvision.transforms.v2/Orchestrator-Fehler), echte Caption im Chat (Screenshot b463_05); 2. Command routet crash-frei aber ohne Antwort-Screenshot -> UNKLAR; Gesamt YELLOW, 0 FAIL. `status: fixed` nur User — vorgeschlagen als READY. Details im Bugfile B-463.
- Offene Findings aus Live-Verify: B-463 (Code+Live gruen, fixed offen), B-464/B-465/B-466/B-467/B-468 (open, ungefixt).
- 2026-06-03 B-469 (NEU, severity high): Native Qt6Core-Crash `0xc0000409` im User-Manual-Test (neues Projekt + Doppel-Import -> parallele "Medien-DB laden"-Tasks + Abbruch-Kaskade + Engine-Swap-bei-nicht-idle-Workern). Nicht B-462/B-463. Read-only Investigation done; Root-Cause Hypothese (QObject/QThread-Lifecycle-Race), nicht auf eine Zeile bewiesen. Bug `wiki/bugs/B-469-...md`. Fix-Plan erstellt (status proposed, kein Code): Repo `docs/superpowers/plans/2026-06-03-b469-native-crash-fix-plan.md`, Vault-Mirror `wiki/synthesis/plan-b469-native-crash-fix-2026-06-03.md`. Staged: Phase 0 Repro (blocking) -> Phase 1 single-flight reload -> Phase 2 idle-enforce project-switch -> Phase 3 re-verify -> Phase 4 conditional teardown-hardening.
- 2026-06-03 B-469 Phase 0 ERGEBNIS: NICHT reproduzierbar — synthetisch 0/~1300 Tasks (`tests/repro/b469_stress_child.py`), GUI 0/8 (pb-gui-tester). Kein verlaessliches Crash-Gate herstellbar. User-Entscheid (4 Optionen): B-469 `status: parked-not-reproducible-monitoring` (WER-Watch). Gap-1 (idle-enforce) read-only verifiziert = bereits abgedeckt (`project_manager` create/open/switch via `_wait_for_tasks_idle`-Guard; Original-Swap lief ohne laufende Tasks). Gap-2 single-flight Media-DB-Reload wird defensiv gebaut (ehrlich: ohne Gate nicht als crash-fixed beweisbar).
- 2026-06-03 B-470 NEU (severity medium, `wiki/bugs/B-470-...md`): Projekt-Erstellen friert UI 13-69s ein. Root code-verifiziert: `services/project_manager.py:130 create_project` ruft blockierendes `_wait_for_tasks_idle(10s)` (busy-poll) + synchrones `set_project`/`init_db` auf dem GUI-Thread (via `project_dialog accept()`). Reproduzierbar. Fix C/D folgen TDD (eine Task nach der anderen): (C) single-flight reload, (D) B-470 UI-Freeze.
