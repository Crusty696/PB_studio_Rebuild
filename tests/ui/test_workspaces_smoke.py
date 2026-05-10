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
# SchnittWorkspace (Redesign 2026-05-09 — replaces EditWorkspace AUTO/REVIEW)
# --------------------------------------------------------------------------

def test_schnitt_initial_state_when_empty(qapp):
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY

    ws = SchnittWorkspace()
    try:
        ws.set_active_project(None)
        assert ws.current_state() == STATE_EMPTY
    finally:
        ws.deleteLater()


def test_schnitt_editor_subtabs_have_correct_titles(qapp):
    from ui.workspaces.schnitt_workspace import SchnittWorkspace

    ws = SchnittWorkspace()
    try:
        titles = [
            ws.editor_view.sub_tabs.tabText(i)
            for i in range(ws.editor_view.sub_tabs.count())
        ]
        assert titles == ["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"]
    finally:
        ws.deleteLater()


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
        # Material & Analyse zeigt Pool/Import und passende Analyse direkt daneben.
        assert w._video_sub_tabs.isHidden()
        assert not w.btn_video_pipeline.isHidden()
        assert not w.btn_analyze_video.isHidden()
        # B-296/R-15: Aliase entfernt, btn_video_pipeline ist Primary.
        assert not hasattr(w, "btn_motion_analysis")
        assert not hasattr(w, "btn_siglip_embeddings")
        assert not w.btn_keyframe_string.isHidden()
        assert not w.keyframe_text.isHidden()
        # Mode-Switch ist no-crash
        w.switch_to_audio()
        assert w.btn_mode_audio.isChecked()
        assert w._audio_sub_tabs.isHidden()
        assert not w.btn_analyze_all.isHidden()
        assert not w.btn_auto_duck.isVisible()
        assert not w.btn_lufs_analyze.isHidden()
        w.switch_to_video()
        assert w.btn_mode_video.isChecked()
    finally:
        w.deleteLater()


def test_material_analysis_workspace_keeps_selection_and_actions_together(qapp):
    from ui.workspaces import ConvertWorkspace, MaterialAnalysisWorkspace, MediaWorkspace

    media = MediaWorkspace()
    convert = ConvertWorkspace()
    w = MaterialAnalysisWorkspace(media, convert)
    try:
        assert w.media_widget is media
        assert w.btn_video_pipeline is media.btn_video_pipeline
        assert w.btn_stems is media.btn_stem_separate
        assert w.btn_keyframe_string is media.btn_keyframe_string
        assert media.video_pool_table.parent() is not None
        assert media.video_analysis_panel.parent() is not None
        assert media.audio_pool_table.parent() is not None
        assert media.audio_analysis_panel.parent() is not None
        assert not convert.btn_standardize_all.isHidden()
        # B-296/R-15: btn_motion_analysis + btn_siglip_embeddings entfernt
        # (Aliase auf _start_video_pipeline). btn_video_pipeline ist Primary.
        for button in (
            media.btn_analyze,
            media.btn_waveform,
            media.btn_key_detect,
            media.btn_lufs_analyze,
            media.btn_structure_detect,
            media.btn_stem_separate,
            media.btn_analyze_all,
            media.btn_analyze_video,
            media.btn_video_pipeline,
            media.btn_keyframe_string,
        ):
            assert not button.isHidden()
            assert len(button.toolTip()) > 80
        assert not hasattr(media, "btn_motion_analysis")
        assert not hasattr(media, "btn_siglip_embeddings")
    finally:
        w.deleteLater()
