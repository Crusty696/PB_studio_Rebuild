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

        def query(self, *models):
            return self

        def filter(self, *args, **kwargs):
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


def test_audio_binder_skips_invalid_signal_connections():
    from ui.controllers.schnitt_audio_binder import SchnittAudioBinder

    class BadSignal:
        def connect(self, _slot):
            raise TypeError("bad signal")

    class StemWorkspace:
        stem_volume_changed = BadSignal()
        stem_mute_toggled = BadSignal()
        play_requested = BadSignal()
        pause_requested = BadSignal()
        stop_requested = BadSignal()
        seek_requested = BadSignal()

        def update_position(self, _seconds):
            pass

        def update_playback_state(self, _state):
            pass

    tab = SimpleNamespace(stem_workspace=StemWorkspace())
    player = SimpleNamespace(
        set_volume=lambda *_args: None,
        set_mute=lambda *_args: None,
        play=lambda *_args: None,
        pause=lambda *_args: None,
        stop=lambda *_args: None,
        seek=lambda *_args: None,
        position_changed=BadSignal(),
        state_changed=BadSignal(),
        playback_finished=BadSignal(),
    )

    binder = SchnittAudioBinder(tab, player)

    assert binder.stem_player is player


def test_audio_binder_forwards_waveform_meta_and_audio_id():
    from ui.controllers.schnitt_audio_binder import SchnittAudioBinder

    calls = []
    tab = SimpleNamespace(
        stem_workspace=SimpleNamespace(),
        set_waveform_data=lambda row, beats: calls.append(("waveform", row, beats)),
        set_structure_markers=lambda markers: calls.append(("markers", markers)),
        set_lufs=lambda value: calls.append(("lufs", value)),
        set_key=lambda key, camelot: calls.append(("key", key, camelot)),
        set_audio_id=lambda audio_id: calls.append(("audio_id", audio_id)),
    )

    binder = SchnittAudioBinder(tab)
    binder.update_waveform("row", beat_positions=None, structure_markers=None)
    binder.update_audio_meta(-13.2, "Fm", "4A")
    binder.set_audio_id(9)

    assert calls == [
        ("waveform", "row", []),
        ("markers", []),
        ("lufs", -13.2),
        ("key", "Fm", "4A"),
        ("audio_id", 9),
    ]
