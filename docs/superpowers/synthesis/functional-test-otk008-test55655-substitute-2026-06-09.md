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
- RL Notes editor opened again.
- Temporary suffix `UNDO_PROBE_2026_06_09` appended.
- `Ctrl+Z` pressed.
- Notes text returned exactly to original value `Test 2026-06-09 Schnitt-Verify test55655`.
- Pacing & Anker regenerate button was clicked once by coordinate and once by pywinauto click on the UIA button object; no QMessageBox/modal dialog appeared in those two mouse-automation attempts.
- Follow-up used UIA `Invoke()` on the same visible enabled button.
- UIA `Invoke()` opened the expected text `Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?`.
- Dialog was dismissed with `Esc`; no regenerate was executed.
- Bug file created and then corrected to `cannot-reproduce`: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-474-schnitt-verify-step-10-regenerate-dialog-missing.md`.

## Evidence

- `test_reports/live_autonomous_20260609_otk008_reverify_schnitt.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_before.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_after_write.png`
- `test_reports/live_autonomous_20260609_otk008_rl_notes_after_reload.png`
- `test_reports/live_autonomous_20260609_otk008_pacing_before_wheel.png`
- `test_reports/live_autonomous_20260609_otk008_cut_rate_before_wheel.png`
- `test_reports/live_autonomous_20260609_otk008_cut_rate_after_wheel.png`
- `test_reports/live_autonomous_20260609_otk008_undo_notes_before.png`
- `test_reports/live_autonomous_20260609_otk008_undo_notes_after_type.png`
- `test_reports/live_autonomous_20260609_otk008_undo_notes_after_ctrlz.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_before_click.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_dialog.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_after_cancel.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_uia_before_click.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_dialog_uia.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_after_cancel_uia.png`
- `test_reports/live_autonomous_20260609_otk008_regenerate_dialog_invoke.png`

## Verified

- App restart after notes write.
- Project reopen through GUI.
- RL Notes persistence after reload for `test55655`.
- SCHNITT tab navigation and existing timeline/editor visibility for `test55655`.
- Combo-wheel protection for visible `cut_rate_combo` in `test55655` substitute run, measured by unchanged combo crop after hover+wheel-scroll.
- Undo behavior inside RL Notes editor in `test55655` substitute run.

## Not Verified

- Fresh project `Schnitt-Verify-2026-05-09` creation.
- Formal source media count of 103 Solo_Natur files.
- Exact audio file `Crusty Progressive Psy Set2.mp3`.
- Formal Phase-12 empty-state/load-state steps.
- Techno preset selection sequence from formal guide.
- Clip lock preservation across pacing regeneration.
- Pacing regeneration dialog trigger by UIA `Invoke()` on `test55655`; the expected QMessageBox text appeared and was dismissed with `Esc`.
- Timeline lock-toggle undo from the formal guide. Only notes-editor undo was verified.

## Honest Result

OTK-008 cannot be marked `fixed` from this run. Substitute verification passed for GUI navigation, RL Notes persistence, combo-wheel protection, and notes-editor undo in `test55655`, but formal Phase-12 criteria remain open.

B-474 status corrected to `cannot-reproduce` as app bug after UIA `Invoke()` showed the expected dialog.
