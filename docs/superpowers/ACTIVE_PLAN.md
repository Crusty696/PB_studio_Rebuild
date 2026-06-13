# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12
next_allowed_task: USER-Live-Verifikation aller 7 Befund-Fixes per echter GUI + status:fixed-Vergabe; danach Wave-4-Entscheid (CRF-024). Stand 2026-06-13: ALLE 7 neuen Live-Befunde code-gefixt (alle code-fix-pending-live-verification, Tests gruen, Commits auf fix-team/2026-06-12-vollaudit): B-523 abb6380f, B-524 afbbac63, B-526 d01db939, B-527 83fcc7d6, B-528 e5161f8a, B-529 497f7201, B-525 d88dbce6(Copy)+20f0e6aa(Layout via Standardisieren-Dialog, recherche-gestuetzt, von Agent live per Screenshot verifiziert: Spalte clean + Dialog funktioniert). status:fixed setzt nur User.
updated: 2026-06-13

## Vorheriger aktiver Plan (pausiert, nicht superseded)

PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09 bleibt `approved-for-implementation` in der Registry. Offene OTK-Tasks (OTK-005, OTK-007, OTK-018, OTK-019, OTK-021, OTK-022) + B-490/B-491-Triage: B-490/B-491 werden in CRF-005 abgearbeitet; Rest wartet auf User-Selektion nach CRF-Abschluss. Pending aus 2026-06-11: commit Task-12 working tree (user-authorized) â€” weiterhin offen.

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
- OTK-010 completed on 2026-06-09. Brain V3 boot health, GpuSerializer init, EmbeddingScheduler active, Brain V3 GUI panel, Brain V3 tests, isolated NVENC 1-frame encode, existing B-276 Brain+NVENC serializer evidence, adopted D-035 Pacing decision, and B-370 GUI Auto-Edit with Studio-Brain flag on `test55655` were verified. GUI Auto-Edit produced 767 segments / 767 cuts and 1447 `mem_decision` rows.
- OTK-011 completed on 2026-06-09 as decision/transfer task. `PB-STUDIO-AREA-AUDIT-2026-05-24` completed all 10 audit areas and final synthesis; user-approved follow-up fixplan already exists as `PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25`. Remaining B-348..B-430 fix/live work is tracked as OTK-007.
- OTK-012 completed on 2026-06-09 as decision/transfer task. Full project file audit completed as read-only static audit; user-approved follow-up fixplan exists as `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` via D-055. Remaining fixplan work is tracked as OTK-005.
- OTK-013 completed on 2026-06-09 as decision/transfer task. Conflict-quality audit completed as static audit; user decision exists as D-058 for FFmpeg resolver fix CQ-004/CQ-005. That follow-up was transferred to OTK-004 and live-verified there. No new broad fixplan was invented for candidate-only findings.
- OTK-014/B-333 completed on 2026-06-09. Root-cause follow-up fixed SigLIP `ModelManager` residency during stage unload. Unit tests passed and real GTX-1060/CUDA pipeline showed SigLIP allocated VRAM dropping from 1723.6 MB before unload to 0.0 MB after unload; RAFT started at 0.0 MB allocated. B-333 marked fixed. OTK-014 remains open; next finding is F-2/B-334.
- OTK-014/B-334 completed on 2026-06-09. Contract tests proved SigLIP/RAFT stages use `gpu_serializer` and `gpu_lock_aware` primitive still behaves; live GTX-1060/CUDA video pipeline e2e passed 3 tests. B-334 marked fixed. OTK-014 remains open; next finding is F-3/B-335.
- OTK-014/B-335 completed on 2026-06-09. Missing Vault bugfile was created. Existing scorer code already normalized by `weight_sum`; new regression test proves the formula. Brain V3 core tests passed 43 tests. B-335 marked fixed. OTK-014 remains open; next finding is F-4/B-336.
- OTK-014/B-336 completed on 2026-06-09. Guard tests passed 15 tests. GTX-1060 SigLIP precision benchmark showed fp16 has no NaN/Inf and uses 1.805 GB peak alloc vs fp32 3.440 GB. Existing fp16 + NaN-Guard + fp32-Fallback policy is verified. B-336 marked fixed. OTK-014 remains open; next finding is F-5/B-337.
- OTK-014/B-337 completed on 2026-06-09. Live GUI opened `test55655`, loaded SCHNITT, selected first timeline clip, and confirmed ClipInspector effect controls visible: brightness, contrast, crossfade. B-337 marked fixed. OTK-014 remains open; next finding is F-6/B-338.
- OTK-014/B-338 completed on 2026-06-09. Live GUI showed Material/Analyse Preflight format controls, selected 3840x2160/50fps/H.265, clicked standardize button, and verified controller created worker args `3840x2160`, `50`, `hevc_nvenc`, `.mp4`. B-338 marked fixed. OTK-014 remains open; next finding is F-7/B-339.
- OTK-014/B-339 completed on 2026-06-09. Regression tests passed and a real `_preprocess_segment()` FFmpeg run produced output with command codec `h264_nvenc`, not `libx264`. Missing Vault bugfile was created. B-339 marked fixed. OTK-014 remains open; next finding is F-8/B-340.
- OTK-014/B-340 completed on 2026-06-09. Missing Vault bugfile was created. Existing video embedder keeps scene/frame alignment by returning `kept_scenes` from `_sample_frames()` and zipping embeddings with those kept scenes. Regression tests passed. B-340 marked fixed. OTK-014 remains open; next finding is F-9/B-341.
- OTK-014/B-341 completed on 2026-06-09. Current Vault state was already `cannot-reproduce` as reachability bug because SCHNITT Audio owns the reachable stem workspace. UI tests passed and confirmed 4-workspace stack plus SCHNITT Audio `stem_workspace`. No product code changed. OTK-014 remains open; next finding is F-10/B-342.
- OTK-014/B-342 completed on 2026-06-09. Missing Vault bugfile was created. Existing startup path quits `_startup_check_thread` on both dialog-exit and success branches and connects thread `finished` to worker/thread `deleteLater`. Regression test passed. B-342 marked fixed. OTK-014 remains open; next finding is F-11/B-343.
- OTK-014/B-343 completed on 2026-06-09. Missing Vault bugfile was created. Existing panel/workspace completion listeners unregister on window teardown. Regression test passed. B-343 marked fixed. OTK-014 remains open; next finding is F-12/B-344.
- OTK-014/B-344 completed on 2026-06-09. Missing Vault bugfile was created. Mood-score path raises `ValueError` on 1152-vs-768 mismatch instead of silently scoring incompatible vectors. Regression test passed. B-344 marked fixed. OTK-014 remains open; next finding is F-13/B-345.
- OTK-014/B-345 completed on 2026-06-09. Missing Vault bugfile was created. Ingest duplicate checks are scoped by `project_id` and `file_path`; cross-project audio/video duplicate regressions passed. B-345 marked fixed. OTK-014 remains open; next finding is F-14/B-346.
- OTK-016 completed on 2026-06-09. B-327 fixed (M4A FFmpeg-Fallback E2E verifiziert). B-331 cannot-reproduce (Chunk-51-Hang nicht reproduzierbar). B-332 fixed (Preview-Fenster am ersten Video verankert). B-197 fixed (F-4 live via OTK-010, F-2/F-3 guard-tests). B-198 fixed (Worker-Pfad live via OTK-010). B-265 wontfix (kein Code-Bug, SB2 dGPU intermittent).
- OTK-017 completed on 2026-06-10. 11 bugs user-confirmed fixed after GUI live-verify: B-458, B-459, B-460, B-463, B-464, B-465, B-466, B-467, B-468, B-470, B-472. B-469 stays parked-not-reproducible-monitoring. Code commits 88fd73b/b9d6b63/a7776d2/8075a92/683f048. New out-of-scope findings B-490 (FK store_scenes_in_db) and B-491 (StructureEnrichment reducer None) filed open.

## Current Next Task

```text
OTK-017 completed 2026-06-10. Next task = user selection among remaining open
OTK tasks (OTK-005, OTK-007, OTK-018, OTK-019, OTK-021, OTK-022) or triage of
new findings B-490 / B-491.
```
