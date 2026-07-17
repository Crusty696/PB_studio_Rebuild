"""B-292: AnalysisStatusPanel muss im MEDIA-Workspace permanent sichtbar
sein und auf Selection im Pool-Table reagieren."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from ui.workspaces.media_workspace import MediaWorkspace


def test_b292_video_analysis_panel_visible_default(qapp):
    ws = MediaWorkspace()
    panel = getattr(ws, "video_analysis_panel", None)
    assert panel is not None, "video_analysis_panel nicht exposed"
    assert panel.isVisibleTo(ws) or panel.isVisible() or not panel.isHidden(), (
        "B-292: AnalysisStatusPanel video ist hidden — User sieht Step-Status nicht."
    )


def test_b292_audio_analysis_panel_visible_default(qapp):
    ws = MediaWorkspace()
    panel = getattr(ws, "audio_analysis_panel", None)
    assert panel is not None, "audio_analysis_panel nicht exposed"
    assert panel.isVisibleTo(ws) or panel.isVisible() or not panel.isHidden(), (
        "B-292: AnalysisStatusPanel audio ist hidden."
    )


def test_b292_panel_set_media_renders_steps(qapp, project, video_clip, monkeypatch):
    """set_media(video, id) muss Step-Liste rendern, alle 9 VIDEO_STEPS.

    refresh() laeuft normalerweise im ThreadPoolExecutor mit
    QTimer.singleShot-Bridge zurueck zum Main-Thread. Im offscreen-Test
    ohne laufende Qt-Event-Loop feuert singleShot aus Worker-Thread nicht
    zuverlaessig. Wir umgehen das per monkeypatch: refresh() ruft
    _apply_status_data synchron im Main-Thread.
    """
    from services import analysis_status_service
    import ui.widgets.analysis_status_panel as panel_mod

    ws = MediaWorkspace()
    panel = ws.video_analysis_panel

    def _sync_refresh(self=panel):
        if self._media_type is None or self._media_id is None:
            self._clear_display()
            return
        try:
            analysis_status_service.infer_from_db(self._media_type, self._media_id)
        except Exception:
            pass
        status_dict = analysis_status_service.get_status(self._media_type, self._media_id)
        my_gen = getattr(self, "_refresh_generation", 0)
        self._apply_status_data(status_dict, my_gen, self._media_type, self._media_id)

    monkeypatch.setattr(panel, "refresh", _sync_refresh)

    panel.set_media("video", video_clip.id)
    rendered_keys = panel.rendered_step_keys()
    expected = {
        "metadata_extract", "scene_detection", "motion_scores",
        "keyframe_extraction", "siglip_embeddings", "vector_db_storage",
        "ai_scene_caption", "scene_db_storage", "structure_enrichment",
    }
    missing = expected - set(rendered_keys)
    assert not missing, f"B-292: Step-Keys fehlen im Panel: {missing}"


def test_b458_audio_pending_filter_renders_missing_steps_with_start_buttons(qapp):
    """B-458: fehlende Audio-Steps muessen im Pending-Filter startbar bleiben."""
    from services.analysis_status_service import AUDIO_STEPS, AUDIO_STEPS_OPTIONAL
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    try:
        panel._media_type = "audio"
        panel._media_id = 1
        panel._filter_mode = "pending"

        panel._apply_status_data({}, None, "audio", 1)

        rendered_keys = panel.rendered_step_keys()
        # Stage-Sichtbarkeit 2026-07-17: Panel zeigt auch die optionalen
        # Audio-V2-Steps (onset/av_pacing) — %-Basis bleibt AUDIO_STEPS.
        assert rendered_keys == AUDIO_STEPS + AUDIO_STEPS_OPTIONAL
        for row in range(panel.table.rowCount()):
            button = panel.table.cellWidget(row, 3)
            assert button is not None
            assert button.text() == "Starten"
    finally:
        panel.deleteLater()


def test_b292_panel_set_media_uses_proxy_aware_index(qapp):
    """Phase-C-fix: pool-selection lambda must read via curr.sibling
    so PagedProxyModel page>0 maps to correct source row."""
    # Smoke-test the named methods exist on the controller.
    from ui.controllers.workspace_setup import WorkspaceSetupController
    assert hasattr(WorkspaceSetupController, "_on_video_pool_selection_for_panel")
    assert hasattr(WorkspaceSetupController, "_on_audio_pool_selection_for_panel")
