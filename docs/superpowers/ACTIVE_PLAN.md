# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
next_allowed_task: Task 1j - B-451 Stem Separator CPU FP16 Clamp Follow-Up
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
- Neuer Blocker: Default pytest gate stoppt bei `tests/test_services/test_stem_separator_audio_decode.py::test_streaming_stem_writer_crossfades_without_full_accumulator`.
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
- Naechster Schritt: Task 1j - B-451 Stem Separator CPU FP16 Clamp Follow-Up.
