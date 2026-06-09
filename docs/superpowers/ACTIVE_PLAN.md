# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
next_allowed_task: OTK-010: Brain V3 / NVIDIA partial checklist follow-up, focusing only on still-open items.
updated: 2026-06-09

## Meaning

Der User hat am 2026-06-09 explizit entschieden, offene Tasks aus Repo-Planen, Vault-Mirrors, Bugfiles und Handoff in einem neuen Masterplan zusammenzufuehren und alte Quellplaene zu archivieren.

Aktiver Plan:

```text
PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
```

Repo-Plan:

```text
docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md
```

Vault-Mirror:

```text
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md
```

Decision:

```text
C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md
```

## Agent Behavior

- Nur diesen neuen Masterplan als Arbeitsautoritaet verwenden.
- Alte Registry-Plaene mit `superseded` nicht mehr als aktive Arbeitsplaene nutzen.
- Alte Plaene bleiben Quellen fuer Belege und Transferhistorie.
- Kein `fixed` setzen ohne echten Live-Workflow plus User-Bestaetigung.
- Keine App-Code-Fixes unter reiner Governance-Konsolidierung.

## Current Status

- Neuer Masterplan erstellt.
- Neue Vault-Decision erstellt.
- Neuer Vault-Mirror erstellt.
- Registry-Umschaltung abgeschlossen.
- Offene Tasks aus Registry, Handoff und gezielten Vault-Bugstatusquellen in OTK-Tasks konsolidiert.
- OTK-001 Governance-Drift im Handoff wurde bereinigt.
- OTK-002 wurde als Weiterfreigabe + Agent-Review ohne Blocker abgeschlossen; kein Beleg, dass der User jede Skill-Datei selbst gelesen hat.
- User hat am 2026-06-09 Fokuswechsel auf OTK-020/Ollama-Recovery autorisiert.
- User supplied filled live verification checklist on 2026-06-09:
  - OTK-020, OTK-003, OTK-004, OTK-008 reported PASS in real GUI workflow.
  - OTK-010, OTK-015, OTK-019 reported PARTIAL.
  - OTK-005, OTK-006, OTK-007, OTK-009, OTK-011, OTK-012, OTK-013, OTK-014, OTK-016, OTK-017, OTK-018, OTK-021, OTK-022 remain decision/scope tasks.
  - Checklist explicitly says no agent-side `fixed` marker; `fixed` remains user-only.
- Agent autonomous GUI verification on 2026-06-09:
  - OTK-020 PASS: ChatDock/Ollama answered in UI; KI-Agent tasks finished.
  - OTK-003 PASS: project `test55655` opened through GUI; SCHNITT timeline, waveform, thumbnails, zoom controls, cut list, and clip inspector observed.
  - OTK-004 PARTIAL PASS: Material/Analyse media table and analyzed clips observed; no new import performed.
  - OTK-008 PASS for GUI navigation: Pacing/Anker, Audio, RL Notes, and Schnitt tabs opened.
  - Evidence saved in `test_reports/live_autonomous_20260609_*.png` and Vault synthesis `functional-test-otk-autonomous-gui-2026-06-09.md`.
- User explicitly approved OTK-020/B-473 `fixed` marker on 2026-06-09.
- User explicitly approved OTK-003/B-471 `fixed` marker on 2026-06-09.
- User gave broad release to continue/status workflows. OTK-004 missing import/live resolver path was executed autonomously through GUI: Video import dialog, 1 MP4 selected, FolderImport and BrainV3Hashing finished, no checked Traceback/ERROR/resolver failure. OTK-004 marked `fixed`.
- OTK-008 substitute GUI verification on 2026-06-09 used existing project `test55655` after user wrote `freigegeben`. RL Notes persistence was verified across app restart/project reload. Combo-wheel protection for `cut_rate_combo` was verified by unchanged crop after hover+wheel-scroll. Notes-editor undo was verified by appending `UNDO_PROBE_2026_06_09`, pressing `Ctrl+Z`, and confirming exact original text returned. Pacing regenerate mouse-automation attempts did not show the dialog, but UIA `Invoke()` on the same visible enabled button did show the expected QMessageBox; B-474 corrected to `cannot-reproduce` as app bug. Formal Phase-12 criteria are still open because the exact audio file, fresh project, expected 103-file source set, empty/load state, lock/regenerate execution, and timeline-lock undo checks were not verified.
- OTK-008 autonomous limit reached: formal Phase-12 completion is blocked because `Crusty Progressive Psy Set2.mp3` was not found and the available Solo_Natur folder contains 124 MP4 files instead of the plan's 103. Status remains `blocked-formal-dataset-missing-substitute-partial-pass`; no `fixed` marker.
- OTK-009 completed on 2026-06-09. B-310 and B-313 were live-verified on `test55655`; SCHNITT timeline, thumbnails, cut list, audio metadata/stems/waveform, and sub-tab tooltip were observed. B-316..B-320 current Vault state is fixed; no remaining contradiction found.
- OTK-010 partial follow-up on 2026-06-09: Brain V3 boot health, GpuSerializer init, EmbeddingScheduler active, Brain V3 GUI panel, Brain V3 tests, and isolated NVENC 1-frame encode verified. Still open: real parallel Brain+NVENC stress, full DJ-mix Brain/Pacing validation, PacingConfig decision.

## Current Next Task

```text
OTK-010: Brain V3 / NVIDIA partial checklist follow-up, focusing only on still-open items.
```
