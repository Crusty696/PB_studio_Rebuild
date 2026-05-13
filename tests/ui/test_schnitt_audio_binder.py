import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_audio_binder_targets_schnitt_stem_workspace():
    _qapp()
    from ui.controllers.schnitt_audio_binder import SchnittAudioBinder
    from ui.workspaces.schnitt.tab_audio import SchnittTabAudio

    tab = SchnittTabAudio()
    calls = []
    tab.stem_workspace.update_for_track = lambda track_id, stems: calls.append((track_id, stems))

    binder = SchnittAudioBinder(tab_audio=tab, stem_player=None)
    binder.update_stems(track_id=7, stem_paths={"vocals": "v.wav"})

    assert calls == [(7, {"vocals": "v.wav"})]


def test_stems_controller_also_updates_schnitt_binder(monkeypatch):
    from ui.controllers import stems as stems_mod

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query(self, model):
            return self

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return SimpleNamespace(
                stem_vocals_path="vocals.wav",
                stem_drums_path="drums.wav",
                stem_bass_path=None,
                stem_other_path=None,
            )

    monkeypatch.setattr(stems_mod, "DBSession", lambda engine: FakeSession())

    old_calls = []
    schnitt_calls = []
    window = SimpleNamespace(
        logger=None,
        stem_player=SimpleNamespace(
            duration=12.5,
            load_stems=lambda stems: True,
            stop=lambda: None,
        ),
        stem_workspace=SimpleNamespace(
            update_for_track=lambda track_id, stems: old_calls.append((track_id, stems)),
            set_duration=lambda duration: None,
        ),
        _schnitt_audio_binder=SimpleNamespace(
            update_stems=lambda track_id, stem_paths: schnitt_calls.append((track_id, stem_paths)),
            set_duration=lambda duration: None,
        ),
        console_text=SimpleNamespace(append=lambda text: None),
    )

    controller = stems_mod.StemsController(window)
    controller._update_stem_workspace(7)

    expected = (
        7,
        {
            "vocals": "vocals.wav",
            "drums": "drums.wav",
            "bass": None,
            "other": None,
        },
    )
    assert old_calls == [expected]
    assert schnitt_calls == [expected]
