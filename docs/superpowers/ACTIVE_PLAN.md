# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
next_allowed_task: Task 6 - Deterministic LLM/Action Boundary Gate
updated: 2026-06-01

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
- Status aktuell: in_progress.
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
- Naechster Schritt: Task 6 - Deterministic LLM/Action Boundary Gate.
