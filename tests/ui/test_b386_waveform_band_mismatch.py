"""B-386: Waveform band length mismatch darf paint nicht crashen.

Befund: ``WaveformGraphicsItem`` nutzt ``len(band_low)`` als num_samples,
indexiert aber band_mid/band_high mit demselben Index. Kuerzere Baender
(korrupte/teilgeschriebene Daten) → IndexError beim Paint.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.waveform_item import WaveformGraphicsItem


def _qapp():
    return QApplication.instance() or QApplication([])


def test_band_lengths_normalized_on_construction():
    _qapp()
    item = WaveformGraphicsItem(
        band_low=[0.1, 0.2, 0.3],
        band_mid=[],
        band_high=[0.9],
        duration=4.0,
    )
    assert len(item._band_low) == 3
    assert len(item._band_mid) == 3
    assert len(item._band_high) == 3


def test_render_tile_does_not_crash_on_band_mismatch():
    _qapp()
    item = WaveformGraphicsItem(
        band_low=[0.1, 0.2],
        band_mid=[],
        band_high=[0.1],
        duration=4.0,
        pixels_per_second=50.0,
        height=50.0,
    )
    img = item._render_tile(0, 64, 50)
    assert img is not None


def test_render_tile_handles_longer_secondary_bands():
    _qapp()
    item = WaveformGraphicsItem(
        band_low=[0.1, 0.2],
        band_mid=[0.5, 0.6, 0.7, 0.8],
        band_high=[0.9, 0.9, 0.9],
        duration=4.0,
        pixels_per_second=50.0,
        height=50.0,
    )
    assert len(item._band_mid) == 2
    assert len(item._band_high) == 2
    img = item._render_tile(0, 64, 50)
    assert img is not None
