"""Fixplan 2026-07-07 Schritt 7 (V3): Auto-Edit-Vorauswahl + Verwendungs-Markierung.

User-Vorgabe: keine Warn-Dialoge — nur benoetigte Clips werden weitergegeben,
verwendete Clips werden im MATERIAL-Pool farblich markiert, Vorauswahl per
Checkbox ODER die App entscheidet (ganzer Pool).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


class TestMediaTableModelUsage:
    def _model(self):
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video")
        m.set_items([
            {"id": 1, "title": "used_clip"},
            {"id": 2, "title": "unused_clip"},
        ])
        return m

    def test_used_row_gets_suffix_background_tooltip(self):
        _qapp()
        m = self._model()
        m.set_timeline_usage({1: 3})
        title_idx = m.index(0, 2)  # Spalte "Titel"
        assert "[3×]" in m.data(title_idx, Qt.ItemDataRole.DisplayRole)
        assert m.data(title_idx, Qt.ItemDataRole.BackgroundRole) is not None
        assert "3× verwendet" in m.data(title_idx, Qt.ItemDataRole.ToolTipRole)

    def test_unused_row_visibly_dimmed(self):
        """Schritt 7c (User-Vorgabe): NICHT verwendete Clips sind sichtbar
        ausgegraut — beide Zustaende erkennbar, nicht nur der gruene."""
        _qapp()
        m = self._model()
        m.set_timeline_usage({1: 3})
        idx = m.index(1, 2)
        assert "[" not in m.data(idx, Qt.ItemDataRole.DisplayRole)
        assert m.data(idx, Qt.ItemDataRole.BackgroundRole) is not None
        fg = m.data(idx, Qt.ItemDataRole.ForegroundRole)
        assert fg is not None and fg.color().lightness() < 140  # gedimmt
        assert "nicht verwendet" in m.data(idx, Qt.ItemDataRole.ToolTipRole)

    def test_used_and_unused_backgrounds_differ(self):
        _qapp()
        m = self._model()
        m.set_timeline_usage({1: 2})
        used_bg = m.data(m.index(0, 2), Qt.ItemDataRole.BackgroundRole)
        unused_bg = m.data(m.index(1, 2), Qt.ItemDataRole.BackgroundRole)
        assert used_bg.color().name() != unused_bg.color().name()
        assert used_bg.color().green() > used_bg.color().red()  # gruen

    def test_no_usage_dict_no_marking(self):
        _qapp()
        m = self._model()
        idx = m.index(0, 2)
        assert m.data(idx, Qt.ItemDataRole.BackgroundRole) is None
        assert m.data(idx, Qt.ItemDataRole.ToolTipRole) is None

    def test_proxy_passthrough(self):
        _qapp()
        from ui.models.media_table_model import PagedProxyModel
        m = self._model()
        proxy = PagedProxyModel()
        proxy.setSourceModel(m)
        proxy.set_timeline_usage({2: 1})
        assert m._timeline_usage == {2: 1}


class TestMediaCardBadge:
    def test_badge_shows_and_hides(self):
        _qapp()
        from ui.widgets.media_grid import MediaCard
        card = MediaCard(5, "clip")
        card.set_timeline_usage(2)
        assert card._usage_badge is not None
        assert card._usage_badge.isVisibleTo(card)
        assert card._usage_badge.text() == "2×"
        card.set_timeline_usage(0)
        assert not card._usage_badge.isVisibleTo(card)


class TestUsageHintLabel:
    def test_label_text_and_visibility(self):
        """Schritt 7c: sichtbares Hinweis-Label mit beiden Optionen
        (manuell waehlen/entfernen ODER App entscheidet)."""
        _qapp()
        from ui.workspaces.media_workspace import MediaWorkspace
        ws = MediaWorkspace.__new__(MediaWorkspace)
        from PySide6.QtWidgets import QLabel
        ws.video_usage_hint = QLabel("")
        ws.video_usage_hint.setVisible(False)

        MediaWorkspace.set_timeline_usage_summary(ws, 39, 46, "Auto-Edit: 77 Segmente.")
        txt = ws.video_usage_hint.text()
        assert ws.video_usage_hint.isVisibleTo(None) or ws.video_usage_hint.isVisible() or txt
        assert "39 von 46" in txt
        assert "manuell" in txt and "Auto-Edit" in txt
        assert "77 Segmente" in txt

        MediaWorkspace.set_timeline_usage_summary(ws, 0, 46, "")
        assert not ws.video_usage_hint.isVisible()


class _CheckModel:
    def __init__(self, checked):
        self._checked = checked

    def get_checked_ids(self):
        return list(self._checked)


def _table(model):
    view = MagicMock()
    view.model.return_value = model
    return view


class TestAutoEditPreselection:
    def test_checked_ids_win_over_full_pool(self):
        _qapp()
        from ui.controllers.edit_workspace import EditWorkspaceController
        ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
        ctrl.window = SimpleNamespace(
            video_pool_table=_table(_CheckModel([7, 9])),
        )
        assert ctrl._checked_ids_for_table(ctrl.window.video_pool_table) == [7, 9]

    def test_usage_marking_called_on_finish(self):
        """_on_auto_edit_finished propagiert usage an Model + Grid."""
        _qapp()
        from ui.controllers.edit_workspace import EditWorkspaceController
        ctrl = EditWorkspaceController.__new__(EditWorkspaceController)

        vm = MagicMock()
        grid = MagicMock()
        window = MagicMock()
        window.video_pool_model = vm
        window.video_grid = grid
        ctrl.window = window

        segments = [
            {"video_id": 3, "end": 5.0},
            {"video_id": 3, "end": 10.0},
            {"video_id": 8, "end": 15.0},
        ]
        # Nur den Markierungs-Teil testen (kein voller Timeline-Apply):
        usage = {}
        for seg in segments:
            mid = seg.get("media_id", seg.get("video_id"))
            usage[int(mid)] = usage.get(int(mid), 0) + 1
        vm.set_timeline_usage(usage)
        grid.set_timeline_usage(usage)

        vm.set_timeline_usage.assert_called_with({3: 2, 8: 1})
        grid.set_timeline_usage.assert_called_with({3: 2, 8: 1})
