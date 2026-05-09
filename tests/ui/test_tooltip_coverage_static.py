"""Static checks for user-facing tooltip coverage in core UI modules."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


REQUIRED_TOOLTIPS: dict[str, tuple[str, ...]] = {
    "ui/controllers/workspace_setup.py": (
        "_btn_context_panel",
        "_btn_open_brain",
        "_btn_toggle_tasks",
        "_btn_toggle_console",
        "_btn_toggle_chat",
        "btn_settings",
        "btn_tools",
    ),
    "ui/dialogs/project_dialog.py": (
        "name_input",
        "path_input",
        "resolution_combo",
        "fps_spin",
    ),
    "ui/workspaces/convert_workspace.py": (
        "convert_resolution",
        "convert_fps",
        "convert_format",
        "btn_standardize_all",
        "effects_clip_combo",
        "brightness_slider",
        "contrast_slider",
        "crossfade_slider",
        "btn_apply_effects",
    ),
    "ui/workspaces/deliver_workspace.py": (
        "export_name_input",
        "resolution_combo",
        "fps_combo",
        "preset_combo",
        "btn_preview",
        "btn_export",
        "btn_refresh_production",
        "btn_preview_play",
        "btn_preview_stop",
    ),
    "ui/workspaces/edit_workspace.py": (
        "vibe_input",
        "cut_rate_combo",
        "style_preset_combo",
        "breakdown_combo",
        "energy_reactivity_slider",
        "energy_reactivity_spin",
        "btn_generate",
        "btn_auto_edit",
        "btn_keyframe_string",
        "btn_add_anchor",
        "btn_remove_anchor",
        "btn_sync_anchors",
        "btn_learn_ai",
    ),
    "ui/workspaces/media_workspace.py": (
        "btn_mode_video",
        "btn_mode_audio",
        "search_input",
        "_video_sub_tabs",
        "_audio_sub_tabs",
    ),
    "ui/workspaces/stems_workspace.py": ("sub_tabs",),
    "ui/widgets/analysis_status_panel.py": (
        "filter_combo",
        "btn_refresh",
        "btn_retry_errors",
    ),
    "ui/widgets/graph_cockpit_tab.py": ("btn_refresh",),
    "ui/widgets/media_grid.py": (
        "_filter_edit",
        "_key_edit",
        "_genre_edit",
        "_sort_combo",
    ),
    "ui/widgets/pacing_decision_explorer.py": (
        "run_combo",
        "btn_refresh",
        "btn_good",
        "btn_bad",
    ),
}


def test_core_ui_controls_have_explicit_tooltips() -> None:
    missing: list[str] = []
    for rel_path, names in REQUIRED_TOOLTIPS.items():
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        for name in names:
            if f"{name}.setToolTip(" not in source and f"self.{name}.setToolTip(" not in source:
                missing.append(f"{rel_path}: {name}")

    assert not missing, "Missing explicit tooltips:\n" + "\n".join(missing)
