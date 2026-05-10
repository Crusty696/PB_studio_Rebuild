"""B-293: Audio-Pool Checkbox + Alle-Button werden von jeder Audio-Analyse
respektiert. Symmetrisch zu Video-Helper."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    """AST-strict slot body extraction."""
    import ast
    src = (REPO / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == slot_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None
            return seg
    raise AssertionError(f"Slot {slot_name} nicht gefunden in {file_rel}")


def test_b293_audio_selected_track_uses_get_checked_ids():
    """R-13: Audio-Helper muss get_checked_ids referenzieren BEVOR selectionModel."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_track")
    assert "get_checked_ids" in body, (
        "B-293: _get_selected_audio_track ignoriert Checkbox — "
        "Audio-Multi-Select tot."
    )
    pos_checked = body.find("get_checked_ids")
    pos_selmodel = body.find("selectionModel")
    if pos_selmodel > 0:
        assert pos_checked < pos_selmodel, (
            "B-293: get_checked_ids muss VOR selectionModel-Fallback stehen."
        )


def test_b293_audio_selected_tracks_plural_exists():
    """B-293: Plural-Variante fuer Batch-Funktionen."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "def _get_selected_audio_tracks(" in src, (
        "B-293: _get_selected_audio_tracks (Plural) fehlt."
    )


def test_b293_audio_selected_tracks_plural_uses_checked_ids():
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_tracks")
    assert "get_checked_ids" in body
    # returns iterable
    assert "list" in body or "return [" in body or "return list" in body


# ---------------------------------------------------------------------------
# R-23 I-1: Behavioral tests (MagicMock-based, verify actual return values).
# ---------------------------------------------------------------------------


def test_b293_plural_returns_all_checked_ids(qapp):
    """Behavioral: get_checked_ids -> [1,2,3] => plural returns [1,2,3]."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = [1, 2, 3]
    ctrl.window.audio_pool_table.model.return_value = model
    result = ctrl._get_selected_audio_tracks()
    assert result == [1, 2, 3]


def test_b293_plural_empty_returns_empty_list(qapp):
    """Behavioral: no checks + no selection => []."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = []
    selmodel = MagicMock()
    selmodel.selectedRows.return_value = []
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value = selmodel
    ctrl.window.audio_pool_table = view
    result = ctrl._get_selected_audio_tracks()
    assert result == []


def test_b293_plural_falls_back_to_selectionmodel(qapp):
    """Behavioral: empty get_checked_ids => fallback to selectionModel rows."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = []
    row1 = MagicMock()
    row1.row.return_value = 0
    row2 = MagicMock()
    row2.row.return_value = 1
    selmodel = MagicMock()
    selmodel.selectedRows.return_value = [row1, row2]

    def idx_func(r, c):
        m = MagicMock()
        m.data.return_value = str(7 + r)  # row0 -> "7", row1 -> "8"
        return m

    model.index.side_effect = idx_func
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value = selmodel
    ctrl.window.audio_pool_table = view
    result = ctrl._get_selected_audio_tracks()
    assert result == [7, 8]


def test_b293_single_returns_first_checked_id(qapp, monkeypatch):
    """Behavioral: get_checked_ids=[42] => single helper returns track tuple
    with id=42. DB-Session via monkeypatch on sqlalchemy.orm.Session."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = [42]
    ctrl.window.audio_pool_table.model.return_value = model

    fake_track = MagicMock()
    fake_track.id = 42
    fake_track.file_path = "/x.mp3"
    fake_track.title = "X"
    fake_track.bpm = 120.0

    fake_session = MagicMock()
    fake_session.get.return_value = fake_track
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_session
    fake_ctx.__exit__.return_value = False

    # _get_selected_audio_track does `from sqlalchemy.orm import Session as DBSession`
    # patch the source module so the local import resolves to our fake.
    import sqlalchemy.orm as _orm_mod
    monkeypatch.setattr(_orm_mod, "Session", lambda eng: fake_ctx)

    result = ctrl._get_selected_audio_track()
    assert result is not None
    assert result[0] == 42
    assert result[1] == "/x.mp3"
    assert result[2] == "X"
    assert result[3] == 120.0


def test_b293_sequential_analyse_uses_plural_helper():
    """B-293: _analyze_all_sequential ruft _get_selected_audio_tracks (Plural-Helper)."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_analyze_all_sequential")
    assert "_get_selected_audio_tracks" in body, (
        "B-293: _analyze_all_sequential ignoriert Plural-Checkbox-Helper."
    )
