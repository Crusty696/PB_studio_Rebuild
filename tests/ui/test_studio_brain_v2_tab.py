from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_studio_brain_window_wires_brain_v2_tab_without_replacing_old_tabs() -> None:
    src = (ROOT / "ui" / "studio_brain_window.py").read_text(encoding="utf-8")
    assert '"Brain v2"' in src
    assert "BrainV2Tab" in src
    assert "PB_STUDIO_BRAIN_V2" in src
    assert "_TAB_LABELS" in src
