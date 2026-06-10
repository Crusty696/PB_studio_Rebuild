"""B-355: Der StemsController-Pfad (Trackwechsel) muss den Onsets-Subtab fuettern.

Vorher uebergab _update_stem_workspace ein SimpleNamespace nur mit id/title/
duration/energy_curve -> der Workspace fand keine onset_*_data -> Onsets-Tab leer.
Fix: Onset-Daten aus der beatgrids-Tabelle in der Session laden und in den Snapshot
packen. (SNR/acoustic_metadata hat keine DB-Quelle -> bleibt None.)
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeQuery:
    def __init__(self, result):
        self._r = result
    def filter(self, *a, **k):
        return self
    def first(self):
        return self._r


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self._i = 0
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def query(self, *a, **k):
        r = self._results[self._i]
        self._i += 1
        return _FakeQuery(r)


def _make_ctrl(update_mock):
    from ui.controllers.stems import StemsController
    ctrl = StemsController.__new__(StemsController)
    ctrl.window = SimpleNamespace(
        stem_player=SimpleNamespace(load_stems=lambda paths: False, duration=0.0,
                                    stop=lambda: None),
        _stems_ws=SimpleNamespace(update_analysis=update_mock),
        console_text=SimpleNamespace(append=lambda s: None),
    )
    return ctrl


def test_b355_controller_feeds_onsets_from_beatgrid():
    track_row = SimpleNamespace(
        id=1, title="Track", duration=10.0, energy_curve=[],
        stem_vocals_path=None, stem_drums_path=None,
        stem_bass_path=None, stem_other_path=None,
    )
    beatgrid_row = SimpleNamespace(
        onset_kick_data=[[1.0, 0.5], [3.0, 0.4]],
        onset_snare_data=[[2.0, 0.6]],
        onset_hihat_data=None,
    )
    update_mock = MagicMock()
    ctrl = _make_ctrl(update_mock)

    with patch("ui.controllers.stems.DBSession",
               lambda eng: _FakeSession([track_row, beatgrid_row])):
        ctrl._update_stem_workspace(1)

    update_mock.assert_called_once()
    snap = update_mock.call_args[0][0]
    assert snap.onset_kick_data == [[1.0, 0.5], [3.0, 0.4]]
    assert snap.onset_snare_data == [[2.0, 0.6]]
    assert snap.onset_hihat_data is None
    assert snap.id == 1


def test_b355_no_beatgrid_passes_none_without_crash():
    track_row = SimpleNamespace(
        id=2, title="T2", duration=5.0, energy_curve=[],
        stem_vocals_path=None, stem_drums_path=None,
        stem_bass_path=None, stem_other_path=None,
    )
    update_mock = MagicMock()
    ctrl = _make_ctrl(update_mock)
    with patch("ui.controllers.stems.DBSession",
               lambda eng: _FakeSession([track_row, None])):  # kein beatgrid
        ctrl._update_stem_workspace(2)
    snap = update_mock.call_args[0][0]
    assert snap.onset_kick_data is None
    assert snap.acoustic_metadata is None
