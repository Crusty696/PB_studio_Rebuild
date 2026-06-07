# B-471 Timeline Layout Recovery - 2026-06-07

Status: code-complete-user-review-pending

Project used:

`C:\Users\David Lochmann\Downloads\video\test55655`

## User Feedback

User reported after prior commits that the timeline still has the same usability problems.

## Changes

- Reduced SCHNITT preview maximum size from 640x360 to 420x236.
- Gave timeline shell minimum height 260 px and higher layout priority.
- Limited cut list height to 130 px.
- Changed timeline `Fit` to preserve readable minimum horizontal scale (`0.25`) instead of compressing 3745s into unreadable stripes.
- Kept vertical fit scale at `1.0`.

## Live App Evidence

Report:

`test_reports/b471_live_test55655_layout_recovery.json`

Screenshot:

`test_reports/b471_live_test55655_layout_recovery.png`

Observed:

- `clip_items=768`
- `waveform_items=1`
- `registered_thumb_paths=5`
- `timeline_shell_size=[1197, 361]`
- `timeline_viewport_size=[1195, 305]`
- `m11_after_fit=0.25`
- `m22_after_fit=1.0`

## Verification

- `pytest tests/ui/test_b471_timeline_usability_recovery.py tests/ui/test_schnitt_timeline_shell.py tests/ui/test_add_clip_command.py -q` -> 20 passed.
- `py_compile ui/timeline.py ui/workspaces/schnitt/tab_schnitt.py ui/undo_commands.py` -> passed.

No `fixed` marker. User review still required.
