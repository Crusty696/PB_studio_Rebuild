from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.orm import Session

from database.models import AudioTrack, Beatgrid, Project, StructureSegment, WaveformData


def test_schnitt_coordinator_feeds_audio_metadata(test_engine):
    from ui.controllers.schnitt_coordinator import SchnittCoordinator

    with Session(test_engine) as s:
        p = Project(name="schnitt-meta", path="C:/tmp/schnitt-meta")
        s.add(p)
        s.flush()
        a = AudioTrack(
            project_id=p.id,
            file_path="song.mp3",
            title="song",
            duration=60.0,
            key="Fm",
            lufs=-9.5,
            key_modulation_data=[{"time": 0.0, "key": "Fm", "camelot": "4A"}],
        )
        s.add(a)
        s.flush()
        waveform = WaveformData(
            audio_track_id=a.id,
            num_samples=2,
            duration=60.0,
            band_low=[0.1, 0.2],
            band_mid=[0.2, 0.3],
            band_high=[0.3, 0.4],
        )
        s.add(waveform)
        s.add(Beatgrid(audio_track_id=a.id, bpm=142.0, beat_positions=[0.0, 0.5, 1.0]))
        s.add(
            StructureSegment(
                audio_track_id=a.id,
                start_time=0.0,
                end_time=8.0,
                label="INTRO",
            )
        )
        s.commit()
        audio_id = a.id

    calls = []
    binder = SimpleNamespace(
        set_audio_id=lambda value: calls.append(("set_audio_id", value)),
        update_waveform=lambda waveform_row, beat_positions, structure_markers: calls.append(
            ("update_waveform", waveform_row.audio_track_id, beat_positions, structure_markers)
        ),
        update_audio_meta=lambda lufs, key, camelot: calls.append(
            ("update_audio_meta", lufs, key, camelot)
        ),
    )

    SchnittCoordinator(audio_binder=binder, db_engine=test_engine).refresh_audio(audio_id)

    assert calls == [
        ("set_audio_id", audio_id),
        (
            "update_waveform",
            audio_id,
            [0.0, 0.5, 1.0],
            [{"start": 0.0, "end": 8.0, "label": "INTRO"}],
        ),
        ("update_audio_meta", -9.5, "Fm", "4A"),
    ]


def test_b321_schnitt_coordinator_uses_column_queries_not_full_json_entities(test_engine):
    from ui.controllers.schnitt_coordinator import SchnittCoordinator

    with Session(test_engine) as s:
        p = Project(name="schnitt-fast", path="C:/tmp/schnitt-fast")
        s.add(p)
        s.flush()
        a = AudioTrack(
            project_id=p.id,
            file_path="song.mp3",
            title="song",
            duration=60.0,
            key="Fm",
            lufs=-9.5,
            key_modulation_data=[{"time": 0.0, "key": "Fm", "camelot": "4A"}],
        )
        s.add(a)
        s.flush()
        s.add(
            WaveformData(
                audio_track_id=a.id,
                num_samples=2,
                duration=60.0,
                band_low=[0.1, 0.2],
                band_mid=[0.2, 0.3],
                band_high=[0.3, 0.4],
            )
        )
        s.add(
            Beatgrid(
                audio_track_id=a.id,
                bpm=142.0,
                beat_positions=[0.0, 0.5],
                downbeat_positions=[0.0],
                energy_per_beat=[0.1, 0.2],
                stem_weighted_energy=[0.2, 0.3],
            )
        )
        s.commit()
        audio_id = a.id

    statements = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", capture_sql)
    try:
        binder = SimpleNamespace(
            set_audio_id=lambda value: None,
            update_waveform=lambda waveform_row, beat_positions, structure_markers: None,
            update_audio_meta=lambda lufs, key, camelot: None,
        )
        SchnittCoordinator(audio_binder=binder, db_engine=test_engine).refresh_audio(audio_id)
    finally:
        event.remove(test_engine, "before_cursor_execute", capture_sql)

    joined_sql = "\n".join(statements)
    assert "downbeat_positions" not in joined_sql
    assert "energy_per_beat" not in joined_sql
    assert "stem_weighted_energy" not in joined_sql
    assert "audio_tracks.file_path" not in joined_sql


def test_audio_combo_change_refreshes_schnitt_coordinator(test_engine, monkeypatch):
    from ui.controllers import edit_workspace as edit_mod

    with Session(test_engine) as s:
        p = Project(name="schnitt-combo", path="C:/tmp/schnitt-combo")
        s.add(p)
        s.flush()
        a = AudioTrack(project_id=p.id, file_path="song.mp3", title="song", duration=60.0)
        s.add(a)
        s.commit()
        audio_id = a.id

    monkeypatch.setattr(edit_mod, "engine", test_engine)
    durations = []
    refreshes = []
    stem_updates = []
    window = SimpleNamespace(
        logger=None,
        audio_combo=SimpleNamespace(currentData=lambda: audio_id),
        pacing_curve=SimpleNamespace(set_duration=lambda duration: durations.append(duration)),
        _schnitt_coordinator=SimpleNamespace(refresh_audio=lambda value: refreshes.append(value)),
        stems=SimpleNamespace(_update_stem_workspace=lambda value: stem_updates.append(value)),
        console_text=SimpleNamespace(append=lambda text: None),
    )

    controller = edit_mod.EditWorkspaceController(window)
    controller._on_audio_combo_changed(0)

    assert durations == [60.0]
    assert refreshes == [audio_id]
    assert stem_updates == [audio_id]


def test_audio_combo_none_clears_schnitt_stems(monkeypatch):
    from ui.controllers import edit_workspace as edit_mod

    calls = []
    window = SimpleNamespace(
        logger=None,
        audio_combo=SimpleNamespace(currentData=lambda: None),
        _schnitt_coordinator=SimpleNamespace(refresh_audio=lambda value: calls.append(("refresh", value))),
        _schnitt_audio_binder=SimpleNamespace(
            update_stems=lambda track_id, stems: calls.append(("stems", track_id, stems)),
            set_duration=lambda duration: calls.append(("duration", duration)),
        ),
    )

    controller = edit_mod.EditWorkspaceController(window)
    controller._on_audio_combo_changed(0)

    assert calls == [
        ("refresh", None),
        ("stems", None, None),
        ("duration", 0.0),
    ]
