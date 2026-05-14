from sqlalchemy.orm import Session as DBSession

from database.models import Project, TimelineEntry


class _TimelineSpy:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_clip(self, **kwargs):
        self.added.append(kwargs)

    def _remove_clip_item(self, entry_id):
        self.removed.append(entry_id)


def test_b319_adding_audio_clip_replaces_existing_master_audio(test_engine, monkeypatch):
    """B-319: A1-Master-Audio darf durch wiederholtes Hinzufuegen nicht duplizieren."""
    import ui.undo_commands as cmd_mod
    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b319-audio-master", path="/tmp/b319-audio-master")
        s.add(p)
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id,
            track="audio",
            media_id=2,
            start_time=0.0,
            end_time=3505.649,
            lane=0,
        ))
        s.commit()
        pid = p.id

    timeline = _TimelineSpy()
    cmd = cmd_mod.AddClipCommand(
        timeline=timeline,
        project_id=pid,
        track_type="audio",
        media_id=2,
        title="Track 2",
        start_time=0.0,
        duration=3505.649,
    )
    cmd.redo()

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="audio")
            .order_by(TimelineEntry.start_time)
            .all()
        )
    assert len(rows) == 1
    assert rows[0].media_id == 2
    assert rows[0].start_time == 0.0
    assert rows[0].end_time == 3505.649

    cmd.undo()

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="audio")
            .order_by(TimelineEntry.start_time)
            .all()
        )
    assert len(rows) == 1
    assert rows[0].media_id == 2
    assert rows[0].start_time == 0.0
    assert rows[0].end_time == 3505.649
