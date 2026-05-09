"""Strukturmarker Sub-Tab Audio (Phase 07 / Task T2.2).

Spec: farbige Rechtecke + Label fuer Intro/Drop/Outro/Buildup/Breakdown
auf der Waveform-Scene.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication, QGraphicsRectItem, QGraphicsSimpleTextItem,
)

from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_set_structure_markers_adds_items():
    _qapp()
    t = SchnittTabAudio()
    markers = [
        {"start": 0.0, "end": 4.0, "label": "Intro"},
        {"start": 4.0, "end": 8.0, "label": "Buildup"},
        {"start": 8.0, "end": 12.0, "label": "Drop"},
        {"start": 12.0, "end": 16.0, "label": "Breakdown"},
        {"start": 16.0, "end": 20.0, "label": "Outro"},
    ]
    t.set_structure_markers(markers)

    items = t.waveform_view.scene().items()
    rects = [it for it in items if isinstance(it, QGraphicsRectItem)]
    texts = [it for it in items if isinstance(it, QGraphicsSimpleTextItem)]
    assert len(rects) == 5
    assert len(texts) == 5
    assert {it.text() for it in texts} == {
        "Intro", "Buildup", "Drop", "Breakdown", "Outro"
    }


def test_set_structure_markers_empty_noop():
    _qapp()
    t = SchnittTabAudio()
    before = len(t.waveform_view.scene().items())
    t.set_structure_markers([])
    after = len(t.waveform_view.scene().items())
    assert before == after


def test_set_structure_markers_skips_invalid():
    _qapp()
    t = SchnittTabAudio()
    markers = [
        {"start": 0.0, "end": 4.0, "label": "Intro"},
        {"start": 5.0, "end": 4.0, "label": "Drop"},   # end <= start
        {"start": 6.0, "end": 8.0},                      # missing label
    ]
    t.set_structure_markers(markers)
    rects = [it for it in t.waveform_view.scene().items()
             if isinstance(it, QGraphicsRectItem)]
    assert len(rects) == 1
