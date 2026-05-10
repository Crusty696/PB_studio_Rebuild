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
