"""Audit 2026-07-27 (Bereich ui-qt) — bestaetigte Funde.

Abgedeckt:
* F2  Auto-Edit ohne Checkbox-Auswahl nutzte nur die ersten 100 Videos
      (MediaTableModel(paginated_fetch=True).rowCount() ist gekappt).
* F3  enter_loading() lief VOR den Abbruch-Guards -> SCHNITT blieb im
      Loading-Overlay haengen, wenn ein Early-Return griff.
* F5  Fortschrittsbalken im AnalysisStatusPanel: Zaehler aus
      filtered_steps, Nenner aus allen Steps; Audio-%-Basis enthielt die
      optionalen V2-Steps.

Kein App-Start, keine DB-Writes, keine Worker.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")


# ---------------------------------------------------------------------------
# F5 — AnalysisStatusPanel Fortschrittsbalken
# ---------------------------------------------------------------------------


class _Entry:
    """Minimaler Stand-in fuer eine AnalysisStatus-Row."""

    def __init__(self, status: str):
        self.status = status
        self.value_summary = {}
        self.error_message = None


def test_f5_progress_bar_ignores_active_filter(qapp):
    """Filter 'Nur Ausstehend' darf den Fortschritt nicht auf 0 druecken."""
    from services.analysis_status_service import VIDEO_STEPS
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    try:
        panel._media_type = "video"
        panel._media_id = 1
        panel._filter_mode = "pending"

        status_dict = {key: _Entry("done") for key in VIDEO_STEPS}
        panel._apply_status_data(status_dict, None, "video", 1)

        # Tabelle ist korrekt leer (nichts ist pending) …
        assert panel.table.rowCount() == 0
        # … der Balken muss trotzdem 100 % zeigen.
        assert panel.progress_bar.maximum() == len(VIDEO_STEPS)
        assert panel.progress_bar.value() == len(VIDEO_STEPS)
    finally:
        panel.deleteLater()


def test_f5_audio_percent_basis_excludes_optional_steps(qapp):
    """Optionale Audio-V2-Steps duerfen nicht in den Nenner (User 2026-07-17)."""
    from services.analysis_status_service import AUDIO_STEPS, AUDIO_STEPS_OPTIONAL
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    try:
        panel._media_type = "audio"
        panel._media_id = 7
        panel._filter_mode = "all"

        status_dict = {key: _Entry("done") for key in AUDIO_STEPS}
        # onset/av_pacing bleiben pending -> vorher 8/10 statt 8/8.
        panel._apply_status_data(status_dict, None, "audio", 7)

        assert panel.table.rowCount() == len(AUDIO_STEPS) + len(AUDIO_STEPS_OPTIONAL)
        assert panel.progress_bar.maximum() == len(AUDIO_STEPS)
        assert panel.progress_bar.value() == len(AUDIO_STEPS)
    finally:
        panel.deleteLater()


def test_f5_partial_progress_still_counts_correctly(qapp):
    """Gegenprobe: unvollstaendige Analyse zeigt weiterhin den Teilstand."""
    from services.analysis_status_service import VIDEO_STEPS
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    try:
        panel._media_type = "video"
        panel._media_id = 2
        panel._filter_mode = "all"

        status_dict = {key: _Entry("done") for key in VIDEO_STEPS[:3]}
        panel._apply_status_data(status_dict, None, "video", 2)

        assert panel.progress_bar.maximum() == len(VIDEO_STEPS)
        assert panel.progress_bar.value() == 3
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------------------
# F2 / F3 — Auto-Edit-Klickpfad
# ---------------------------------------------------------------------------


def _make_auto_edit_controller(monkeypatch, *, audio_id, video_items):
    """EditWorkspaceController mit echtem, paginiertem Video-Pool-Model."""
    from ui.controllers.edit_workspace import EditWorkspaceController
    from ui.models.media_table_model import MediaTableModel

    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    ctrl.window = MagicMock()

    model = MediaTableModel(media_type="Video", paginated_fetch=True)
    model.set_items(video_items)
    ctrl.window.video_pool_model = model
    ctrl.window.audio_combo.currentData = lambda: audio_id
    ctrl.window.transition_combo.currentIndex = lambda: 0
    ctrl.window.cut_rate_combo.currentIndex = lambda: 2
    ctrl.window.breakdown_combo.currentIndex = lambda: 0
    ctrl.window.energy_reactivity_spin.value = lambda: 50
    ctrl.window.vibe_input.text = lambda: ""
    ctrl.window.pacing_curve.get_all_densities = lambda: []

    ctrl._require_schnitt_action = lambda _label: True
    ctrl._checked_ids_for_table = lambda _table: []
    ctrl._collect_anchors_from_ui = lambda: []

    started = {}

    def _fake_start(**kwargs):
        started.update(kwargs)

    ctrl.start_auto_edit_worker = _fake_start

    # Kein DB-Zugriff: transition_type-Persistenz haengt an einer aktiven
    # Projekt-ID.
    import database

    monkeypatch.setattr(database, "get_active_project_id", lambda: None)

    # SettingsStore nicht anfassen (liest/schreibt sonst echte Settings).
    import services.settings_store as settings_store

    class _Store:
        @staticmethod
        def get_nested(*_args, **kwargs):
            return kwargs.get("default", False)

    monkeypatch.setattr(settings_store, "get_settings_store", lambda: _Store())

    return ctrl, model, started


def test_f2_auto_edit_uses_full_pool_beyond_fetch_window(qapp, monkeypatch):
    """103 Clips im Pool -> alle 103 gehen in den Auto-Edit, nicht 100."""
    items = [{"id": i, "title": f"clip{i}"} for i in range(1, 104)]
    ctrl, model, started = _make_auto_edit_controller(
        monkeypatch, audio_id=1, video_items=items
    )

    # Vorbedingung: das Model exponiert wirklich nur den Fetch-Ausschnitt.
    assert model.rowCount() == 100
    assert len(items) == 103

    ctrl._auto_edit_to_beat()

    assert started, "start_auto_edit_worker wurde nicht erreicht"
    assert len(started["video_ids"]) == 103
    assert started["video_ids"] == [i["id"] for i in items]


def test_f2_usage_summary_total_is_not_capped(qapp, monkeypatch):
    """Verwendungs-Zusammenfassung meldet den vollen Pool als Gesamtzahl."""
    from ui.controllers.edit_workspace import EditWorkspaceController
    from ui.models.media_table_model import MediaTableModel

    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    ctrl.window = MagicMock()

    model = MediaTableModel(media_type="Video", paginated_fetch=True)
    model.set_items([{"id": i, "title": f"clip{i}"} for i in range(1, 104)])
    ctrl.window.video_pool_model = model
    ctrl.window.video_grid = None

    captured = {}

    media_ws = MagicMock()
    media_ws.set_timeline_usage_summary = lambda used, total, extra=None: captured.update(
        {"used": used, "total": total}
    )
    ctrl.window._media_ws = media_ws

    ctrl._refresh_timeline_usage_marking(usage={1: 2})

    assert captured["total"] == 103


def test_f3_enter_loading_not_called_when_audio_missing(qapp, monkeypatch):
    """Early-Return ohne Audio darf den SCHNITT nicht in STATE_LOADING sperren."""
    items = [{"id": 1, "title": "clip1"}]
    ctrl, _model, started = _make_auto_edit_controller(
        monkeypatch, audio_id=None, video_items=items
    )
    ws = MagicMock()
    ctrl.window._schnitt_ws = ws

    ctrl._auto_edit_to_beat()

    assert not started, "Worker haette nicht starten duerfen"
    assert not ws.enter_loading.called, (
        "enter_loading() lief trotz Abbruch — SCHNITT bleibt im Loading-Overlay"
    )


def test_f3_enter_loading_not_called_when_pool_empty(qapp, monkeypatch):
    """Gleiches fuer den leeren Video-Pool (async Media-Reload noch unterwegs)."""
    ctrl, _model, started = _make_auto_edit_controller(
        monkeypatch, audio_id=1, video_items=[]
    )
    ws = MagicMock()
    ctrl.window._schnitt_ws = ws

    ctrl._auto_edit_to_beat()

    assert not started
    assert not ws.enter_loading.called


def test_f3_enter_loading_still_runs_on_success(qapp, monkeypatch):
    """Gegenprobe: im echten Startpfad muss das Loading-Overlay weiter kommen."""
    items = [{"id": 1, "title": "clip1"}]
    ctrl, _model, started = _make_auto_edit_controller(
        monkeypatch, audio_id=1, video_items=items
    )
    ws = MagicMock()
    ctrl.window._schnitt_ws = ws

    ctrl._auto_edit_to_beat()

    assert started, "Worker-Start fehlt"
    assert ws.enter_loading.called, "Loading-Overlay wurde nicht mehr gesetzt"
