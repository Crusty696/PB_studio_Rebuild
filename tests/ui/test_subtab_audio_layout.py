"""Layout-Test fuer Sub-Tab Audio (Phase 07 / Task 7.1 + Tier-2 T2.3)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_widgets_present():
    _qapp()
    t = SchnittTabAudio()
    assert t.waveform_view is not None
    assert t.stem_workspace is not None
    assert t.lufs_label is not None
    assert t.key_label is not None


def test_lufs_and_key_in_header_above_waveform():
    """T2.3: LUFS+Tonart liegen in einer HBox OBERHALB der Waveform."""
    _qapp()
    t = SchnittTabAudio()
    layout: QVBoxLayout = t.layout()
    assert isinstance(layout, QVBoxLayout)

    # Header-Row finden: enthaelt lufs_label
    header_idx = None
    waveform_idx = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        sub = item.layout() if hasattr(item, "layout") else None
        if isinstance(sub, QHBoxLayout):
            for j in range(sub.count()):
                w = sub.itemAt(j).widget()
                if w is t.lufs_label:
                    header_idx = i
        widget = item.widget()
        if widget is t.waveform_view:
            waveform_idx = i

    assert header_idx is not None, "Header mit LUFS muss existieren"
    assert waveform_idx is not None, "Waveform-View muss im Layout liegen"
    assert header_idx < waveform_idx, "Header muss ueber der Waveform sein"
