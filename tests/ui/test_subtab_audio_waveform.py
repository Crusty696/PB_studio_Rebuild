"""Waveform-Einbindung Sub-Tab Audio (Phase 07 / Task T2.1).

Spec: WaveformGraphicsItem mit echten DB-Feldern (band_low/mid/high,
duration, beat_positions). Plan-Abweichung dokumentiert: Plan nennt
``waveform_json``/``beats_json``/``structure_json`` -- real existieren
``WaveformData.band_low/mid/high`` + ``Beatgrid.beat_positions`` +
``StructureSegment``-Rows. Test verwendet die realen Felder.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from ui.waveform_item import WaveformGraphicsItem
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def _fake_waveform_row(duration: float = 4.0):
    n = 64
    return SimpleNamespace(
        band_low=[0.5] * n,
        band_mid=[0.4] * n,
        band_high=[0.3] * n,
        duration=duration,
        num_samples=n,
    )


def test_set_audio_id_none_clears_scene():
    _qapp()
    t = SchnittTabAudio()
    t.render_grid_lines([0.1, 0.2, 0.3])
    assert len(t.waveform_view.scene().items()) >= 3
    t.set_audio_id(None)
    assert len(t.waveform_view.scene().items()) == 0


def test_set_waveform_data_adds_waveform_item():
    _qapp()
    t = SchnittTabAudio()
    wave = _fake_waveform_row(duration=4.0)
    beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]

    t.set_waveform_data(wave, beats)

    items = t.waveform_view.scene().items()
    has_wave = any(isinstance(it, WaveformGraphicsItem) for it in items)
    assert has_wave, "Scene muss WaveformGraphicsItem enthalten"


def test_set_audio_id_with_data_replaces_old_items():
    _qapp()
    t = SchnittTabAudio()
    wave1 = _fake_waveform_row(duration=2.0)
    t.set_waveform_data(wave1, [0.5, 1.0, 1.5])
    n_first = len(t.waveform_view.scene().items())
    assert n_first >= 1

    # zweiter Aufruf -- alte Items sollen weg sein
    wave2 = _fake_waveform_row(duration=3.0)
    t.set_waveform_data(wave2, [1.0, 2.0])
    items = t.waveform_view.scene().items()
    waveforms = [it for it in items if isinstance(it, WaveformGraphicsItem)]
    assert len(waveforms) == 1, "alte WaveformGraphicsItems muessen geclear't sein"
