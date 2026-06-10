"""B-286: Editor-Header 'Timeline generieren' muss vor dem Ueberschreiben einer
bestehenden Timeline bestaetigen lassen.

Vorher war ``btn_generate`` direkt an ``_generate_timeline`` verdrahtet und
ueberschrieb die Timeline ohne Warnung. Fix: ``_generate_timeline_from_button``
zeigt ``confirm_regenerate`` wenn bereits Clips existieren; der confirm-freie
Live-Pfad ``pacing_curve.curve_changed -> _generate_timeline`` bleibt unberuehrt.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _ctrl(clip_items):
    from ui.controllers.edit_workspace import EditWorkspaceController
    c = EditWorkspaceController.__new__(EditWorkspaceController)
    c.window = SimpleNamespace(timeline_view=SimpleNamespace(clip_items=clip_items))
    c._generate_timeline = MagicMock()
    return c


def test_b286_button_confirms_when_timeline_exists_and_aborts_on_no():
    c = _ctrl(clip_items=[object(), object()])  # Timeline vorhanden
    with patch("ui.workspaces.schnitt.regenerate_dialog.confirm_regenerate",
               return_value=False) as cr:
        c._generate_timeline_from_button()
    cr.assert_called_once()
    c._generate_timeline.assert_not_called()


def test_b286_button_generates_when_confirmed():
    c = _ctrl(clip_items=[object()])
    with patch("ui.workspaces.schnitt.regenerate_dialog.confirm_regenerate",
               return_value=True):
        c._generate_timeline_from_button()
    c._generate_timeline.assert_called_once()


def test_b286_empty_timeline_generates_without_confirm():
    c = _ctrl(clip_items=[])  # keine Timeline -> nichts zu ueberschreiben
    with patch("ui.workspaces.schnitt.regenerate_dialog.confirm_regenerate") as cr:
        c._generate_timeline_from_button()
    cr.assert_not_called()
    c._generate_timeline.assert_called_once()


def test_b286_button_wired_to_confirm_path():
    """workspace_setup verdrahtet btn_generate auf den Confirm-Button-Handler."""
    from ui.controllers.workspace_setup import WorkspaceSetupController
    src = inspect.getsource(WorkspaceSetupController)
    assert "btn_generate.clicked.connect" in src
    assert "_generate_timeline_from_button" in src
