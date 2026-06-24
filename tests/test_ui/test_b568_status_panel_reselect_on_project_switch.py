"""B-568 regression: analysis-status panel must re-select after project switch.

`MediaWorkspace.ensure_status_panel_selection` (B-473) auto-selected the first
media only when the panel held *no* selection (`_media_id is None`). After a
project switch the panel still held the previous project's media_id, so the
guard skipped re-selection and the panel showed the stale status (e.g. "0 of 8")
until the user manually clicked a track again (live-captured 2026-06-24).

Fix: also re-select when the held media_id is no longer present in the current
pool. Behavioral test — calls the method unbound with stub panels (no Qt).
"""

from __future__ import annotations

from types import SimpleNamespace

from ui.workspaces.media_workspace import MediaWorkspace


class _FakePanel:
    def __init__(self, media_id=None):
        self._media_id = media_id
        self.calls: list[tuple] = []

    def set_media(self, media_type, media_id, title=""):
        self._media_id = media_id
        self.calls.append((media_type, media_id, title))


def _ws(v_id=None, a_id=None):
    return SimpleNamespace(
        video_analysis_panel=_FakePanel(v_id),
        audio_analysis_panel=_FakePanel(a_id),
    )


def test_reselects_when_held_media_not_in_pool() -> None:
    # stale ids from a previous project -> must re-select the new pool's first item
    ws = _ws(v_id=99, a_id=88)
    MediaWorkspace.ensure_status_panel_selection(
        ws, [{"id": 1, "title": "v"}], [{"id": 2, "title": "a"}]
    )
    assert ws.video_analysis_panel._media_id == 1
    assert ws.audio_analysis_panel._media_id == 2


def test_selects_when_nothing_selected() -> None:
    ws = _ws(v_id=None, a_id=None)
    MediaWorkspace.ensure_status_panel_selection(ws, [{"id": 5}], [{"id": 6}])
    assert ws.video_analysis_panel._media_id == 5
    assert ws.audio_analysis_panel._media_id == 6


def test_keeps_valid_existing_selection() -> None:
    # held media still present in pool -> do NOT yank the user's selection
    ws = _ws(v_id=1, a_id=2)
    MediaWorkspace.ensure_status_panel_selection(
        ws, [{"id": 1}, {"id": 3}], [{"id": 2}]
    )
    assert ws.video_analysis_panel.calls == []
    assert ws.audio_analysis_panel.calls == []
