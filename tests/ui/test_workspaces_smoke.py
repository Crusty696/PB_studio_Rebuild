"""Smoke-Tests fuer ui/workspaces/ — Drift-Stop fuer 2518 LOC ohne dezidierte Tests.

Pattern: offscreen Qt + plain QApplication (kein qtbot), wie
``tests/ui/test_studio_brain_window.py`` / ``test_inspector_panel.py``.

Jeder Workspace bekommt einen Konstruktions-Test der verifiziert, dass die
publizierten Widget-Attribute existieren — das sind die Hooks, die
``ui/controllers/*`` und ``ui/controllers/workspace_setup.py`` per Name
verdrahten. Wenn diese Attribute weggehen, crasht die App beim PBWindow-
Aufbau, nicht hier — also fangen wir den Drift hier ab.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QWidget


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return _ensure_qapp()


# --------------------------------------------------------------------------
# ConvertWorkspace
# --------------------------------------------------------------------------

def test_convert_workspace_constructs_and_exposes_batch_widgets(qapp):
    from ui.workspaces import ConvertWorkspace

    w = ConvertWorkspace()
    try:
        assert isinstance(w, QWidget)
        # Convert ist nur Preflight/Standardisierung im Hauptflow.
        assert w._tabs.count() == 1, "ConvertWorkspace darf im Hauptflow nur Preflight zeigen"
        assert w._tabs.tabText(0) == "PREFLIGHT"
        # Batch-Tab Widgets, die controllers/convert.py per Name anspricht
        for attr in (
            "convert_resolution",
            "convert_fps",
            "convert_format",
            "btn_standardize_all",
            "convert_log",
        ):
            assert hasattr(w, attr), f"ConvertWorkspace.{attr} fehlt"
        # Effekte-Tab Widgets
        for attr in (
            "effects_clip_combo",
            "brightness_slider",
            "contrast_slider",
            "crossfade_slider",
            "btn_apply_effects",
        ):
            assert hasattr(w, attr), f"ConvertWorkspace.{attr} fehlt"
        assert hasattr(w, "expert_tools")
        assert not w.expert_tools.isVisible(), "Clip-Effekte muessen standardmaessig versteckt sein"
    finally:
        w.deleteLater()


# --------------------------------------------------------------------------
# DeliverWorkspace
# --------------------------------------------------------------------------

def test_deliver_workspace_constructs_and_exposes_export_widgets(qapp):
    from ui.workspaces import DeliverWorkspace

    w = DeliverWorkspace()
    try:
        assert isinstance(w, QWidget)
        assert w._tabs.count() == 1, "DeliverWorkspace darf im Hauptflow nur Export zeigen"
        assert w._tabs.tabText(0) == "EXPORT"
        for attr in (
            "export_name_input",
            "resolution_combo",
            "fps_combo",
            "preset_combo",
            "btn_export",
            "btn_preview",
            "btn_preview_play",
            "btn_preview_stop",
            "production_info",
        ):
            assert hasattr(w, attr), f"DeliverWorkspace.{attr} fehlt"
        assert hasattr(w, "export_log")
        assert not w.export_log.isVisible(), "Rohes Export-Protokoll gehoert ins Kontextpanel/Expert-UI"
    finally:
        w.deleteLater()


# --------------------------------------------------------------------------
# StemsWorkspace
# --------------------------------------------------------------------------

def test_stems_workspace_constructs_and_exposes_subtabs(qapp):
    from ui.workspaces import StemsWorkspace

    w = StemsWorkspace()
    try:
        assert isinstance(w, QWidget)
        # DAW-Player-Wrapper
        assert hasattr(w, "stem_widget"), "StemsWorkspace.stem_widget fehlt"
        # Sub-Tabs (ENERGIE | ONSETS | SNR)
        assert hasattr(w, "sub_tabs")
        assert w.sub_tabs.count() == 3, "StemsWorkspace muss 3 Sub-Tabs haben"
        # update_analysis(None) darf nicht crashen — Robustheit gegen leere Tracks
        w.update_analysis(None)
    finally:
        w.deleteLater()


# --------------------------------------------------------------------------
# EditWorkspace
# --------------------------------------------------------------------------

def test_edit_workspace_constructs_and_exposes_timeline_widgets(qapp):
    from ui.workspaces import EditWorkspace

    w = EditWorkspace()
    try:
        assert isinstance(w, QWidget)
        assert hasattr(w, "set_workflow_stage")
        w.set_workflow_stage("auto")
        assert w._tabs.count() == 1
        assert w._tabs.tabText(0) == "AUTO-SCHNITT"
        assert not w.btn_thumbs_up.isVisible()
        assert not w.btn_thumbs_down.isVisible()
        w.set_workflow_stage("review")
        assert w._tabs.count() == 1
        assert w._tabs.tabText(0) == "REVIEW"
        assert not w.btn_keyframe_string.isHidden()
        assert not w.keyframe_text.isHidden()
        # Cross-Tab-Wiring-Endpunkte (TimelineView + Inspector)
        for attr in (
            "timeline_view",
            "clip_inspector",
            "inspector_panel",  # Alias auf clip_inspector
            "video_preview",
            "btn_preview_play",
            "btn_preview_stop",
            "btn_generate",
            "btn_auto_edit",
            "audio_combo",
            "video_combo",
            "vibe_input",
            "cut_rate_combo",
        ):
            assert hasattr(w, attr), f"EditWorkspace.{attr} fehlt"
        # inspector_panel ist Alias auf clip_inspector (P9-Step4)
        assert w.inspector_panel is w.clip_inspector
        assert hasattr(w, "expert_tools")
        assert not w.expert_tools.isVisible(), "KI/Debug-Werkzeuge muessen aus Hauptflow raus"
    finally:
        w.deleteLater()


# --------------------------------------------------------------------------
# MediaWorkspace
# --------------------------------------------------------------------------

def test_media_workspace_constructs_with_video_audio_modes(qapp):
    from ui.workspaces import MediaWorkspace

    w = MediaWorkspace()
    try:
        assert isinstance(w, QWidget)
        # Mode-Toggle (VIDEO | AUDIO)
        assert hasattr(w, "btn_mode_video")
        assert hasattr(w, "btn_mode_audio")
        assert w.btn_mode_video.isChecked(), "Default-Mode muss VIDEO sein"
        # Stacked-Widget mit 2 Pages (VIDEO + AUDIO)
        assert hasattr(w, "mode_stack")
        assert w.mode_stack.count() == 2
        # Shared Bottom-Bar Button
        assert hasattr(w, "btn_add_to_timeline")
        # Quellen zeigt nur Pool/Import. Analyse-Pipelines leben im Analyse-Workspace.
        assert w._video_sub_tabs.isHidden()
        assert not w.btn_video_pipeline.isVisible()
        assert not w.btn_analyze_video.isVisible()
        assert not w.btn_motion_analysis.isVisible()
        assert not w.btn_siglip_embeddings.isVisible()
        # Mode-Switch ist no-crash
        w.switch_to_audio()
        assert w.btn_mode_audio.isChecked()
        assert w._audio_sub_tabs.isHidden()
        assert not w.btn_analyze_all.isVisible()
        assert not w.btn_auto_duck.isVisible()
        assert not w.btn_lufs_analyze.isVisible()
        w.switch_to_video()
        assert w.btn_mode_video.isChecked()
    finally:
        w.deleteLater()


def test_analysis_workspace_owns_audio_video_steps(qapp):
    from ui.workspaces import AnalysisWorkspace, MediaWorkspace, StemsWorkspace

    media = MediaWorkspace()
    stems = StemsWorkspace()
    w = AnalysisWorkspace(stems, media)
    try:
        assert w.tabs.count() == 3
        assert w.tabs.tabText(0) == "Audio"
        assert w.tabs.tabText(1) == "Video"
        assert w.tabs.tabText(2) == "Stems / Status"
        for button in (
            media.btn_analyze,
            media.btn_waveform,
            media.btn_key_detect,
            media.btn_lufs_analyze,
            media.btn_structure_detect,
            media.btn_stem_separate,
            media.btn_analyze_all,
            media.btn_analyze_video,
            media.btn_motion_analysis,
            media.btn_siglip_embeddings,
            media.btn_video_pipeline,
        ):
            assert not button.isHidden()
            assert len(button.toolTip()) > 80
    finally:
        w.deleteLater()
