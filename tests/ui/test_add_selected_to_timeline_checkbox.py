"""B-321: Checkbox-markierte Medien muessen fuer Timeline-Add zaehlen."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


class _Cell:
    def __init__(self, value):
        self._value = value

    def data(self):
        return self._value


class _Row:
    def __init__(self, row: int):
        self._row = row

    def row(self) -> int:
        return self._row


class _TableModel:
    def __init__(self, checked_ids=None, rows=None):
        self._checked_ids = checked_ids or []
        self._rows = rows or []

    def get_checked_ids(self):
        return list(self._checked_ids)

    def index(self, row, col):
        return _Cell(self._rows[row][col])


def _view(model, selected_rows=None):
    selection = MagicMock()
    selection.selectedRows.return_value = [_Row(r) for r in (selected_rows or [])]
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value = selection
    return view


def test_b321_collects_all_checked_video_ids_before_row_selection(qapp):
    """Checked video IDs sind die eigentliche Nutzer-Markierung."""
    from ui.controllers.edit_workspace import EditWorkspaceController

    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    ctrl.window = SimpleNamespace(
        audio_pool_table=_view(_TableModel(checked_ids=[])),
        video_pool_table=_view(
            _TableModel(
                checked_ids=[30, 10],
                rows=[
                    ["", "99", "Blue selected"],
                    ["", "30", "Checked C"],
                    ["", "10", "Checked A"],
                ],
            ),
            selected_rows=[0],
        ),
    )

    assert ctrl._collect_timeline_add_requests() == [
        {"media_type": "Video", "media_id": 30, "title": None},
        {"media_type": "Video", "media_id": 10, "title": None},
    ]


def test_b321_falls_back_to_single_selected_row_when_nothing_checked(qapp):
    """Bestehendes Single-Row-Verhalten bleibt Fallback."""
    from ui.controllers.edit_workspace import EditWorkspaceController

    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    ctrl.window = SimpleNamespace(
        audio_pool_table=_view(_TableModel(checked_ids=[])),
        video_pool_table=_view(
            _TableModel(
                checked_ids=[],
                rows=[
                    ["", "41", "Selected clip"],
                ],
            ),
            selected_rows=[0],
        ),
    )

    assert ctrl._collect_timeline_add_requests() == [
        {"media_type": "Video", "media_id": 41, "title": "Selected clip"},
    ]
