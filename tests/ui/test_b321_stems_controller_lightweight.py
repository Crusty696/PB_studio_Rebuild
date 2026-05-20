from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.orm import Session

from database.models import AudioTrack, Beatgrid, Project


class FakeStemPlayer:
    duration = 60.0

    def load_stems(self, stem_paths):
        return True

    def stop(self):
        return None


def test_b321_stems_controller_uses_lightweight_audio_query(test_engine, monkeypatch) -> None:
    from ui.controllers import stems as stems_mod

    with Session(test_engine) as s:
        p = Project(name="stems-fast", path="C:/tmp/stems-fast")
        s.add(p)
        s.flush()
        a = AudioTrack(
            project_id=p.id,
            file_path="song.mp3",
            title="song",
            duration=60.0,
            stem_vocals_path="C:/tmp/vocals.wav",
            energy_curve=[[0.1], [0.2]],
        )
        s.add(a)
        s.flush()
        s.add(
            Beatgrid(
                audio_track_id=a.id,
                bpm=142.0,
                beat_positions=[0.0],
                energy_per_beat=[0.1],
            )
        )
        s.commit()
        audio_id = a.id

    monkeypatch.setattr(stems_mod, "engine", test_engine)
    statements = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    window = SimpleNamespace(
        stem_player=FakeStemPlayer(),
        stem_workspace=SimpleNamespace(
            update_for_track=lambda track_id, stem_paths: None,
            set_duration=lambda duration: None,
        ),
        _schnitt_audio_binder=SimpleNamespace(
            update_stems=lambda track_id, stem_paths: None,
            set_duration=lambda duration: None,
        ),
        _stems_ws=SimpleNamespace(update_analysis=lambda track: None),
        console_text=SimpleNamespace(append=lambda text: None),
    )
    controller = stems_mod.StemsController(window)

    event.listen(test_engine, "before_cursor_execute", capture_sql)
    try:
        controller._update_stem_workspace(audio_id)
    finally:
        event.remove(test_engine, "before_cursor_execute", capture_sql)

    joined_sql = "\n".join(statements)
    assert "beatgrids" not in joined_sql
    assert "video_clips" not in joined_sql
    assert "audio_tracks.file_path" not in joined_sql
