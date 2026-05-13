# SCHNITT Hidden Host Audit - B-310

Date: 2026-05-13
Status: code-fix-pending-live-verification

## Scope

Task 7 from `docs/superpowers/plans/2026-05-13-schnitt-usability-wiring-rebuild/README.md`.

Command used:

```powershell
rg -n "edit_workspace\.|_on_schnitt_|_generate_timeline|_auto_edit_to_beat|_on_audio_combo_changed|_on_video_combo_changed|_add_anchor|_sync_anchors|_learn_anchor|_show_keyframe|_apply_style|clip_moved" ui\controllers\workspace_setup.py ui\controllers\schnitt_controller.py ui\workspaces\schnitt -S
```

## Current State

The visible SCHNITT UI is `SchnittWorkspace`. The old hidden workspace host is not reintroduced.

Remaining issue: many visible SCHNITT controls still route through `EditWorkspaceController`. This is now explicit technical debt, not an invisible hidden widget. B-310 Tasks 1-6 already moved data/context/audio/action gating into focused SCHNITT services and binders.

## Remaining Routes

| Route | Current target | Decision |
|---|---|---|
| `btn_add_to_timeline.clicked` | `edit_workspace._add_selected_to_timeline` | Keep temporarily. This is material-pool to timeline action, not only SCHNITT editor. Move later to `SchnittTimelineBinder`. |
| `request_auto_edit_with_profile` | `edit_workspace._on_schnitt_auto_edit_request` | Keep temporarily. Task 5 added `SchnittActionBinder` guard before worker path. Move worker orchestration later to `SchnittCoordinator`. |
| `request_regenerate` | `edit_workspace._on_schnitt_regenerate_request` | Keep temporarily. Task 5 guard is active. Move later to `SchnittCoordinator`. |
| `btn_preview_play.clicked` | `edit_workspace._toggle_preview_play` | Move later to `SchnittTimelineBinder` or preview binder. Thin UI action only. |
| `video_combo.currentIndexChanged` | `edit_workspace._on_video_combo_changed` | Move later to `SchnittCoordinator.refresh_video`. Current path still loads real preview data. |
| `audio_combo.currentIndexChanged` | `edit_workspace._on_audio_combo_changed` | Partially moved. Task 3 feeds `SchnittCoordinator.refresh_audio`; old method still also updates pacing duration. |
| `btn_generate.clicked` | `edit_workspace._generate_timeline` | Keep temporarily. Task 5 blocks missing preconditions before Loading/Worker. Move to `SchnittCoordinator.generate_timeline`. |
| `btn_auto_edit.clicked` | `edit_workspace._auto_edit_to_beat` | Keep temporarily. Task 5 blocks missing preconditions before Loading/Worker. Move to `SchnittCoordinator.auto_edit`. |
| `btn_add_anchor.clicked` | `edit_workspace._add_anchor_dialog` | Move later to `SchnittTimelineBinder`. |
| `btn_remove_anchor.clicked` | `edit_workspace._remove_selected_anchor` | Move later to `SchnittTimelineBinder`. |
| `btn_sync_anchors.clicked` | `edit_workspace._sync_anchors` | Move later to `SchnittTimelineBinder`. |
| `btn_learn_ai.clicked` | `edit_workspace._learn_anchor_as_ai_rule` | Move later to `SchnittActionBinder` or RL binder. |
| `btn_keyframe_string.clicked` | `edit_workspace._show_keyframe_strings` | Media action. Keep until MEDIA keyframe UI is separated from SCHNITT route. |
| `pacing_curve.curve_changed` | `edit_workspace._generate_timeline` | Keep temporarily. Guard active. Move to `SchnittCoordinator.generate_timeline`. |
| `style_combo.currentIndexChanged` | `edit_workspace._apply_style_preset` | Move later to `SchnittActionBinder`/pacing binder. |
| `timeline_view.clip_moved` | `edit_workspace._on_timeline_clip_moved` | Move later to `SchnittTimelineBinder`. |
| RL feedback buttons | `edit_workspace._rl_feedback_positive/_negative` | Move later to RL binder. |
| `video_preview.position_changed` | `edit_workspace._on_preview_position_changed` | Move later to preview/timeline binder. |
| `video_preview.playback_state_changed` | `edit_workspace._on_preview_state_changed` | Move later to preview/timeline binder. |

## Already Extracted In B-310

- `services/schnitt_context.py`: read-only SCHNITT context.
- `ui/controllers/schnitt_audio_binder.py`: stems/audio tab binder.
- `ui/controllers/schnitt_coordinator.py`: audio metadata feed.
- `ui/controllers/schnitt_action_binder.py`: action precondition gating.
- `ui/workspaces/schnitt/timeline_shell.py`: visible timeline shell.

## Next Move

Task 8 remains live verification. Code is not `fixed`.

Recommended follow-up after Task 8: new plan slice `SchnittTimelineBinder` to remove preview, timeline, anchor and worker routes from `EditWorkspaceController` in small verified steps.
