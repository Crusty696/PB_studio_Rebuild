"""Phase 06 / Task 6.1: Layout-Test fuer Sub-Tab 'Pacing & Anker'."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker


def _qapp():
    return QApplication.instance() or QApplication([])


def test_widgets_present():
    _qapp()
    t = SchnittTabPacingAnker()
    assert t.pacing_curve is not None
    assert t.cut_rate_combo.count() == 5
    assert t.style_combo.count() >= 4
    assert t.breakdown_combo.count() == 3
    assert t.reactivity_slider is not None
    assert t.reactivity_spin is not None
    assert t.vibe_input is not None
    assert t.btn_regenerate is not None
    assert t.anchor_list is not None
    assert t.btn_add_anchor is not None
    assert t.btn_remove_anchor is not None
    assert t.btn_sync_anchors is not None
    assert t.btn_learn_ai is not None


def test_btn_regenerate_label():
    _qapp()
    t = SchnittTabPacingAnker()
    assert "neuen Pacing" in t.btn_regenerate.text()
