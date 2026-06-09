# OTK-008 Substitute Live Verification — test55655

Date: 2026-06-09
Task: `OTK-008: SCHNITT Workspace Redesign Phase 12; autonomous GUI PASS, formal Phase-12 criteria still open.`
Status: `partial-substitute-live-verification-formal-open`

## Scope

The formal Phase-12 guide expects a fresh project `Schnitt-Verify-2026-05-09`, audio `Crusty Progressive Psy Set2.mp3`, and a Solo_Natur source set with 103 files.

Facts checked before this run:

- Exact audio file `Crusty Progressive Psy Set2.mp3` was not found under `C:\Users\David Lochmann`.
- Only derived stems were found under `C:\Users\David Lochmann\Downloads\video\test55655\storage\stems\htdemucs_ft\Crusty_Progressive Psy Set2\`.
- The available Solo_Natur folder count was 124 MP4 files, not the plan's 103.
- User selected `test55655` and wrote `freigegeben`; this authorized a substitute verification against existing project `C:\Users\David Lochmann\Downloads\video\test55655`.

## Executed GUI Path

- PB Studio restarted.
- Existing project `test55655` opened through GUI.
- SCHNITT workflow opened.
- Timeline view observed with existing editor state, clip inspector, audio/video lanes, markers, cut list.
- RL Notes tab opened.
- Note text entered: `Test 2026-06-09 Schnitt-Verify test55655`.
- App closed.
- App restarted.
- Existing project `test55655` reopened through GUI.
- SCHNITT workflow opened again.
- RL Notes tab opened again.
- Same note text was still present after reload.
- Pacing & Anker tab opened.
- Mouse hovered over `cut_rate_combo` without clicking and wheel-scrolled.
- Crop of `cut_rate_combo` before/after wheel-scroll was pixel-identical (`diff_sum=0.0`).

## Evidence

- `test_reports/live_autonomous_20260609_otk008_reverify_schnitt.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_before.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_after_write.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_after_reload.png`
- `test_reports/live_autonomous_20260609_otk008_pacing_before_wheel.png`
- `test_reports/live_autonomous_20260609_otk008_cut_rate_before_wheel.png`
- `test_reports/live_autonomous_20260609_otk008_cut_rate_after_wheel.png`

## Verified

- App restart after notes write.
- Project reopen through GUI.
- RL Notes persistence after reload for `test55655`.
- SCHNITT tab navigation and existing timeline/editor visibility for `test55655`.
- Combo-wheel protection for visible `cut_rate_combo` in `test55655` substitute run, measured by unchanged combo crop after hover+wheel-scroll.

## Not Verified

- Fresh project `Schnitt-Verify-2026-05-09` creation.
- Formal source media count of 103 Solo_Natur files.
- Exact audio file `Crusty Progressive Psy Set2.mp3`.
- Formal Phase-12 empty-state/load-state steps.
- Techno preset selection sequence from formal guide.
- Clip lock preservation across pacing regeneration.
- Pacing regeneration dialog end-to-end.
- Undo behavior.

## Honest Result

OTK-008 cannot be marked `fixed` from this run. Substitute verification passed for GUI navigation, RL Notes persistence, and combo-wheel protection in `test55655`, but formal Phase-12 criteria remain open.
