"""virt-M4 (D-066): Guards gegen unnoetige Voll-Reloads pro Workspace-Klick.

Watchdog-Beweis (workspace_switch_perf, 2026-07-10): refresh_audio lief bei
JEDEM Workspace-Klick komplett durch — scene().clear() + 3x ~55k-Float-
Waveform-Query + Rebuild im Main-Thread => 25-29s-Freezes ab Zyklus 1.
Fix: gleiches Audio mit bereits gebundener Waveform => No-op; solange keine
Waveform gebunden ist (Analyse evtl. ausstehend), wird weiter geladen.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

from database.models import WaveformData
from ui.controllers.schnitt_coordinator import SchnittCoordinator


class _FakeBinder:
    def __init__(self):
        self.set_audio_calls: list = []
        self.waveform_calls: list = []
        self.meta_calls: list = []

    def set_audio_id(self, audio_id):
        self.set_audio_calls.append(audio_id)

    def update_waveform(self, waveform, beats, markers):
        self.waveform_calls.append(waveform)

    def update_audio_meta(self, lufs, key, camelot=None):
        self.meta_calls.append((lufs, key, camelot))


def _add_waveform(db_session, audio_track):
    wf = WaveformData(
        audio_track_id=audio_track.id,
        num_samples=4,
        duration=10.0,
        band_low=json.dumps([0.1, 0.2, 0.3, 0.4]),
        band_mid=json.dumps([0.1, 0.2, 0.3, 0.4]),
        band_high=json.dumps([0.1, 0.2, 0.3, 0.4]),
    )
    db_session.add(wf)
    db_session.commit()


def test_m4_refresh_audio_noop_on_same_bound_audio(test_engine, db_session, audio_track):
    _add_waveform(db_session, audio_track)
    binder = _FakeBinder()
    coord = SchnittCoordinator(binder, test_engine)

    coord.refresh_audio(audio_track.id)
    assert len(binder.set_audio_calls) == 1
    assert binder.waveform_calls and binder.waveform_calls[-1] is not None

    # Gleiches Audio, Waveform gebunden -> No-op (kein clear, keine Queries).
    coord.refresh_audio(audio_track.id)
    assert len(binder.set_audio_calls) == 1

    # force=True erzwingt den Reload (z.B. nach expliziter Invalidierung).
    coord.refresh_audio(audio_track.id, force=True)
    assert len(binder.set_audio_calls) == 2

    # Anderes Audio (None) -> laeuft durch und resettet den Merker.
    coord.refresh_audio(None)
    assert len(binder.set_audio_calls) == 3
    coord.refresh_audio(audio_track.id)
    assert len(binder.set_audio_calls) == 4


def test_m4_refresh_audio_retries_while_waveform_missing(test_engine, db_session, audio_track):
    # KEINE WaveformData-Row: Analyse-Ergebnis steht noch aus -> jeder
    # Aufruf laedt erneut (kein Skip), damit die spaetere Waveform erscheint.
    binder = _FakeBinder()
    coord = SchnittCoordinator(binder, test_engine)

    coord.refresh_audio(audio_track.id)
    coord.refresh_audio(audio_track.id)
    assert len(binder.set_audio_calls) == 2

    # Waveform kommt an (Analyse fertig) -> naechster Lauf bindet sie ...
    _add_waveform(db_session, audio_track)
    coord.refresh_audio(audio_track.id)
    assert binder.waveform_calls[-1] is not None
    # ... und ab jetzt greift der No-op-Guard.
    coord.refresh_audio(audio_track.id)
    assert len(binder.set_audio_calls) == 3
