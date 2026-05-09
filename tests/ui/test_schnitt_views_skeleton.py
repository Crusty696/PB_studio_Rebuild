"""Skeleton-Tests fuer SchnittEmptyView + SchnittLoadingView (Phase 04 / Task 4.1)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.empty_view import SchnittEmptyView
from ui.workspaces.schnitt.loading_view import SchnittLoadingView


def _qapp():
    return QApplication.instance() or QApplication([])


def test_empty_view_has_four_presets_and_custom():
    _qapp()
    v = SchnittEmptyView()
    keys = v.preset_keys()
    assert keys == ["Techno", "Cinematic", "House", "Festival"]
    assert v.btn_custom is not None
    assert v.btn_custom.text() == "Eigene Einstellungen…"


def test_empty_view_emits_preset_signal():
    _qapp()
    v = SchnittEmptyView()
    received = []
    v.preset_selected.connect(received.append)
    v._buttons["Techno"].click()
    assert received == ["Techno"]


def test_loading_view_initial_text_and_setter():
    _qapp()
    v = SchnittLoadingView()
    assert v.status_label.text() != ""
    v.set_stage("cut_calc", 0.42)
    assert "Schnitte" in v.status_label.text()
    assert v.progress_bar.value() == 42
