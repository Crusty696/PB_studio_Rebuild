"""B-293..B-296 Phase G: Audit-Greps gegen Regression (R-12/R-13/R-14/R-15)."""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    src = (REPO / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == slot_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None
            return seg
    raise AssertionError(f"Slot {slot_name} nicht gefunden in {file_rel}")


def test_r13_audio_video_helper_symmetry():
    """R-13: Audio-Helper haben get_checked_ids first, symmetrisch zu Video."""
    audio_body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_track")
    assert "get_checked_ids" in audio_body, "R-13: audio single helper missing checkbox-first"
    audio_plural = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_tracks")
    assert "get_checked_ids" in audio_plural, "R-13: audio plural helper missing checkbox-first"


def test_r14_no_silent_return_in_schnitt_adapter():
    """R-14: SchnittController-Adapter ruft Auto-Fill, kein silent return."""
    src = (REPO / "ui/controllers/edit_workspace.py").read_text(encoding="utf-8")
    assert "_ensure_combos_filled_from_project" in src, (
        "R-14: _ensure_combos_filled_from_project fehlt — silent-return Risiko."
    )
    # Adapter MUST call helper (direct OR via _guard_combos_or_notify wrapper).
    auto_edit = _slot_body("ui/controllers/edit_workspace.py", "_on_schnitt_auto_edit_request")
    assert (
        "_ensure_combos_filled_from_project" in auto_edit
        or "_guard_combos_or_notify" in auto_edit
    )
    regen = _slot_body("ui/controllers/edit_workspace.py", "_on_schnitt_regenerate_request")
    assert (
        "_ensure_combos_filled_from_project" in regen
        or "_guard_combos_or_notify" in regen
    )


def test_r15_no_duplicate_alias_buttons():
    """R-15: btn_motion_analysis + btn_siglip_embeddings nicht mehr in MediaWorkspace + nicht mehr in workspace_setup connect."""
    media_src = (REPO / "ui/workspaces/media_workspace.py").read_text(encoding="utf-8")
    # only comments may remain (R-15 documentation hint).
    code_lines = [
        ln for ln in media_src.splitlines()
        if "btn_motion_analysis" in ln or "btn_siglip_embeddings" in ln
    ]
    non_comment = [ln for ln in code_lines if not ln.lstrip().startswith("#")]
    assert non_comment == [], (
        f"R-15: btn_motion_analysis/btn_siglip_embeddings noch im Code (nicht nur Kommentar): {non_comment}"
    )
    setup_src = (REPO / "ui/controllers/workspace_setup.py").read_text(encoding="utf-8")
    assert "btn_motion_analysis.clicked.connect" not in setup_src
    assert "btn_siglip_embeddings.clicked.connect" not in setup_src


def test_b293_sequential_multi_track_loop_present():
    """C-1 fix: _analyze_all_sequential prozessiert ALLE Tracks (Batch-Queue)."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_analyze_all_sequential")
    has_loop = "for track_id in" in body or "for tid in" in body
    has_queue = "_batch_queue" in body or "_process_next_batch_track" in body
    assert has_loop or has_queue, (
        "B-293 C-1: _analyze_all_sequential muss alle Tracks abarbeiten."
    )
    # The deferred-comment must be GONE.
    assert "Batch-Multi-Track deferred" not in body


def test_b295_cut_list_panel_module_exists():
    """B-295: CutListPanel + get_cut_list existieren."""
    panel_src = (REPO / "ui/widgets/cut_list_panel.py").read_text(encoding="utf-8")
    assert "class CutListPanel" in panel_src
    assert "def set_project" in panel_src
    assert "def rendered_row_count" in panel_src
    svc_src = (REPO / "services/timeline_service.py").read_text(encoding="utf-8")
    assert "def get_cut_list" in svc_src


def test_b296_onboarding_banner_module_exists():
    """B-296: OnboardingBanner widget + MediaWorkspace integration."""
    banner_src = (REPO / "ui/widgets/onboarding_banner.py").read_text(encoding="utf-8")
    assert "class OnboardingBanner" in banner_src
    media_src = (REPO / "ui/workspaces/media_workspace.py").read_text(encoding="utf-8")
    assert "OnboardingBanner" in media_src
    assert "self.onboarding_banner" in media_src
