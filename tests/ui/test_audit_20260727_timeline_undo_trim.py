"""Audit 2026-07-27 (Bereich timeline-export): Undo-Vollstaendigkeit + Trim-Klemmen.

Abgedeckte, per Skeptiker bestaetigte Befunde:

* ApplyAutoEditCommand.undo verlor das ``locked``-Flag (Backup-Dict ohne Feld).
* RemoveClipCommand.undo stellte den Clip ohne seine ClipAnchors wieder her.
* AddClipCommand.undo liess die vom Overlap-Resolver verschobenen Nachbarn
  verschoben stehen (Luecke -> Export-Gap-Abbruch).
* Trim rechts war unbegrenzt: ``source_end`` lief ueber die Clip-Laenge und
  brach den GESAMTEN Export ab (``_source_duration_from_entry``).
* Trim links ueber den Quellanfang hinaus liess den Timeline-Slot lang,
  waehrend das Quellfenster auf 0.0 geklemmt wurde -> stiller A/V-Drift.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DBSession

from database.models import ClipAnchor, Project, TimelineEntry, VideoClip


class _TimelineSpy:
    """Minimaler Ersatz fuer InteractiveTimeline (keine Qt-Abhaengigkeit)."""

    def __init__(self):
        self.added = []
        self.removed = []
        self.reloads = []
        self.trim_syncs = []
        self.lock_visuals = []

    def add_clip(self, **kwargs):
        self.added.append(kwargs)

    def _remove_clip_item(self, entry_id):
        self.removed.append(entry_id)

    def load_from_db(self, project_id):
        self.reloads.append(project_id)

    def _sync_clip_after_trim(self, entry_id, start, end):
        self.trim_syncs.append((entry_id, start, end))

    def _sync_clip_lock_visual(self, entry_id, locked):
        self.lock_visuals.append((entry_id, locked))


def _mk_project(test_engine, name: str) -> int:
    with DBSession(test_engine) as s:
        project = Project(name=name, path=f"/tmp/{name}")
        s.add(project)
        s.commit()
        return project.id


def _mk_video_clip(test_engine, project_id: int, duration: float) -> int:
    with DBSession(test_engine) as s:
        clip = VideoClip(
            project_id=project_id,
            file_path=f"/tmp/clip-{project_id}-{duration}.mp4",
            duration=duration,
        )
        s.add(clip)
        s.commit()
        return clip.id


# ---------------------------------------------------------------------------
# Befund: ApplyAutoEditCommand.undo verliert locked
# ---------------------------------------------------------------------------

def test_apply_auto_edit_undo_restores_locked_flag(test_engine, monkeypatch):
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-autoedit-locked")
    with DBSession(test_engine) as s:
        s.add_all([
            TimelineEntry(project_id=pid, track="video", media_id=1,
                          start_time=0.0, end_time=4.0, lane=0,
                          source_start=0.0, source_end=4.0, locked=True),
            TimelineEntry(project_id=pid, track="video", media_id=2,
                          start_time=4.0, end_time=8.0, lane=0,
                          source_start=0.0, source_end=4.0, locked=False),
        ])
        s.commit()

    timeline = _TimelineSpy()
    cmd = cmd_mod.ApplyAutoEditCommand(
        timeline=timeline,
        project_id=pid,
        new_segments=[{
            "media_id": 3,
            "start": 8.0,
            "end": 12.0,
            "source_start": 0.0,
            "source_end": 4.0,
        }],
    )
    cmd.redo()

    # Praemisse: der gelockte Clip ueberlebt den Apply.
    with DBSession(test_engine) as s:
        locked_after_redo = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video", media_id=1)
            .one()
        )
        assert locked_after_redo.locked is True

    cmd.undo()

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.media_id)
            .all()
        )
        locked_by_media = {row.media_id: bool(row.locked) for row in rows}

    assert locked_by_media.get(1) is True, (
        "Undo des Auto-Edits hat das locked-Flag verloren "
        f"(Zustand: {locked_by_media})"
    )
    assert locked_by_media.get(2) is False


# ---------------------------------------------------------------------------
# Befund: RemoveClipCommand.undo stellt ClipAnchors nicht wieder her
# ---------------------------------------------------------------------------

def test_remove_clip_undo_restores_clip_anchors(test_engine, monkeypatch):
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-remove-anchors")
    media_id = _mk_video_clip(test_engine, pid, 30.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=2.0, end_time=8.0, lane=0,
                              source_start=0.0, source_end=6.0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.add_all([
            ClipAnchor(timeline_entry_id=entry_id, time_offset=1.25,
                       label="A", color="#FF3333"),
            ClipAnchor(timeline_entry_id=entry_id, time_offset=4.5,
                       label="B", color="#33FF33"),
        ])
        s.commit()

    timeline = _TimelineSpy()
    cmd = cmd_mod.RemoveClipCommand(timeline=timeline, entry_id=entry_id)
    cmd.redo()

    # Praemisse: ON DELETE CASCADE raeumt die Anker beim Loeschen wirklich weg.
    with DBSession(test_engine) as s:
        assert s.query(ClipAnchor).filter_by(timeline_entry_id=entry_id).count() == 0

    cmd.undo()

    with DBSession(test_engine) as s:
        restored = (
            s.query(ClipAnchor)
            .filter_by(timeline_entry_id=entry_id)
            .order_by(ClipAnchor.time_offset)
            .all()
        )
        offsets = [round(a.time_offset, 3) for a in restored]
        labels = [a.label for a in restored]

    assert offsets == [1.25, 4.5], (
        f"Undo hat die ClipAnchors nicht wiederhergestellt (gefunden: {offsets})"
    )
    assert labels == ["A", "B"]


def test_remove_clip_undo_does_not_duplicate_anchors_on_repeat(test_engine, monkeypatch):
    """Redo/Undo-Zyklus darf die Anker nicht vervielfachen."""
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-remove-anchors-repeat")
    media_id = _mk_video_clip(test_engine, pid, 30.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=0.0, end_time=5.0, lane=0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.add(ClipAnchor(timeline_entry_id=entry_id, time_offset=2.0,
                         label="X", color="#FF3333"))
        s.commit()

    cmd = cmd_mod.RemoveClipCommand(timeline=_TimelineSpy(), entry_id=entry_id)
    cmd.redo()
    cmd.undo()
    cmd.redo()
    cmd.undo()

    with DBSession(test_engine) as s:
        assert s.query(ClipAnchor).filter_by(timeline_entry_id=entry_id).count() == 1


# ---------------------------------------------------------------------------
# Befund: AddClipCommand.undo laesst verschobene Nachbarn stehen
# ---------------------------------------------------------------------------

def test_add_clip_undo_restores_neighbours_shifted_by_overlap_resolver(
    test_engine, monkeypatch
):
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-add-undo-shift")
    with DBSession(test_engine) as s:
        s.add_all([
            TimelineEntry(project_id=pid, track="video", media_id=1,
                          start_time=0.0, end_time=10.0, lane=0),
            TimelineEntry(project_id=pid, track="video", media_id=2,
                          start_time=10.0, end_time=20.0, lane=0),
        ])
        s.commit()

    timeline = _TimelineSpy()
    cmd = cmd_mod.AddClipCommand(
        timeline=timeline,
        project_id=pid,
        track_type="video",
        media_id=3,
        title="Drop",
        start_time=5.0,
        duration=4.0,
    )
    cmd.redo()

    # Praemisse: der Resolver hat den Nachbarn (media 2) kaskadierend
    # nach rechts geschoben.
    with DBSession(test_engine) as s:
        neighbour = (s.query(TimelineEntry)
                     .filter_by(project_id=pid, media_id=2).one())
        assert neighbour.start_time > 10.0

    cmd.undo()

    with DBSession(test_engine) as s:
        rows = {
            row.media_id: (row.start_time, row.end_time)
            for row in s.query(TimelineEntry).filter_by(
                project_id=pid, track="video").all()
        }

    assert 3 not in rows, "Undo hat den hinzugefuegten Clip nicht entfernt"
    assert rows[1] == (0.0, 10.0)
    assert rows[2] == (10.0, 20.0), (
        "Undo hat die vom Overlap-Resolver verschobenen Nachbarn nicht "
        f"zurueckgesetzt (Zustand: {rows})"
    )


def test_add_clip_undo_leaves_untouched_neighbours_alone(test_engine, monkeypatch):
    """Anhaengen hinter dem letzten Clip verschiebt nichts -> kein Reload-Pfad."""
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-add-undo-noshift")
    with DBSession(test_engine) as s:
        s.add(TimelineEntry(project_id=pid, track="video", media_id=1,
                            start_time=0.0, end_time=10.0, lane=0))
        s.commit()

    timeline = _TimelineSpy()
    cmd = cmd_mod.AddClipCommand(
        timeline=timeline,
        project_id=pid,
        track_type="video",
        media_id=2,
        title="Append",
        start_time=10.0,
        duration=5.0,
    )
    cmd.redo()
    cmd.undo()

    with DBSession(test_engine) as s:
        rows = {
            row.media_id: (row.start_time, row.end_time)
            for row in s.query(TimelineEntry).filter_by(
                project_id=pid, track="video").all()
        }
    assert rows == {1: (0.0, 10.0)}
    assert timeline.removed, "Ohne Shift muss der schlanke Item-Remove-Pfad greifen"


# ---------------------------------------------------------------------------
# Befund: Trim rechts ohne Obergrenze -> source_end > clip duration
# ---------------------------------------------------------------------------

def test_trim_right_clamps_source_end_to_media_duration(test_engine, monkeypatch):
    import ui.undo_commands as cmd_mod
    from services.export._common import _source_duration_from_entry

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-trim-right")
    media_id = _mk_video_clip(test_engine, pid, 20.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=0.0, end_time=10.0, lane=0,
                              source_start=10.0, source_end=20.0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.commit()

    timeline = _TimelineSpy()
    # Rechts-Trim auf 15s Slot -> source_end waere 10 + 15 = 25 > 20.
    cmd = cmd_mod.TrimClipCommand(
        timeline=timeline,
        entry_id=entry_id,
        old_start=0.0, old_end=10.0,
        old_source_start=10.0, old_source_end=20.0,
        new_start=0.0, new_end=15.0,
        new_source_start=10.0, new_source_end=25.0,
    )
    cmd.redo()

    with DBSession(test_engine) as s:
        row = s.get(TimelineEntry, entry_id)
        assert row.source_end == 20.0, (
            f"source_end laeuft ueber die Clip-Laenge: {row.source_end}"
        )
        assert row.end_time == 10.0, (
            "Timeline-Slot muss um den geklemmten Ueberschuss mitgekuerzt "
            f"werden, ist aber {row.end_time}"
        )
        # Der Export darf danach nicht mehr abbrechen.
        assert _source_duration_from_entry(row, 10.0, clip_duration=20.0) == 10.0

    cmd.undo()
    with DBSession(test_engine) as s:
        row = s.get(TimelineEntry, entry_id)
        assert (row.start_time, row.end_time) == (0.0, 10.0)
        assert (row.source_start, row.source_end) == (10.0, 20.0)


def test_trim_right_within_source_is_untouched(test_engine, monkeypatch):
    """Ein regulaerer Rechts-Trim innerhalb des Materials bleibt exakt."""
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-trim-right-ok")
    media_id = _mk_video_clip(test_engine, pid, 20.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=0.0, end_time=4.0, lane=0,
                              source_start=2.0, source_end=6.0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.commit()

    cmd = cmd_mod.TrimClipCommand(
        timeline=_TimelineSpy(),
        entry_id=entry_id,
        old_start=0.0, old_end=4.0,
        old_source_start=2.0, old_source_end=6.0,
        new_start=0.0, new_end=7.0,
        new_source_start=2.0, new_source_end=9.0,
    )
    cmd.redo()

    with DBSession(test_engine) as s:
        row = s.get(TimelineEntry, entry_id)
        assert (row.start_time, row.end_time) == (0.0, 7.0)
        assert (row.source_start, row.source_end) == (2.0, 9.0)


# ---------------------------------------------------------------------------
# Befund: Trim links ueber den Quellanfang hinaus -> Slot laenger als Quelle
# ---------------------------------------------------------------------------

def test_trim_left_beyond_source_start_shifts_start_time(test_engine, monkeypatch):
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-trim-left")
    media_id = _mk_video_clip(test_engine, pid, 20.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=10.0, end_time=14.0, lane=0,
                              source_start=1.0, source_end=5.0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.commit()

    # Links-Trim um 3s: new_source_start = 1 - 3 = -2 (existiert nicht).
    cmd = cmd_mod.TrimClipCommand(
        timeline=_TimelineSpy(),
        entry_id=entry_id,
        old_start=10.0, old_end=14.0,
        old_source_start=1.0, old_source_end=5.0,
        new_start=7.0, new_end=14.0,
        new_source_start=-2.0, new_source_end=5.0,
    )
    cmd.redo()

    with DBSession(test_engine) as s:
        row = s.get(TimelineEntry, entry_id)
        start_time, end_time = row.start_time, row.end_time
        source_start, source_end = row.source_start, row.source_end

    slot = end_time - start_time
    source_span = source_end - source_start

    assert source_start == 0.0  # B-653 Fix 4 klemmt weiterhin
    assert source_span == 5.0
    assert slot == source_span, (
        "Timeline-Slot und Quellfenster laufen auseinander "
        f"(slot={slot}, source={source_span}) -> stiller A/V-Drift im Export"
    )
    assert (start_time, end_time) == (9.0, 14.0)

    cmd.undo()
    with DBSession(test_engine) as s:
        row = s.get(TimelineEntry, entry_id)
        assert (row.start_time, row.end_time) == (10.0, 14.0)
        assert (row.source_start, row.source_end) == (1.0, 5.0)


def test_trim_left_redo_is_idempotent(test_engine, monkeypatch):
    """Zweites redo() nach undo() darf nicht erneut klemmen."""
    import ui.undo_commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "audit-trim-left-idem")
    media_id = _mk_video_clip(test_engine, pid, 20.0)
    with DBSession(test_engine) as s:
        entry = TimelineEntry(project_id=pid, track="video", media_id=media_id,
                              start_time=10.0, end_time=14.0, lane=0,
                              source_start=1.0, source_end=5.0)
        s.add(entry)
        s.flush()
        entry_id = entry.id
        s.commit()

    cmd = cmd_mod.TrimClipCommand(
        timeline=_TimelineSpy(),
        entry_id=entry_id,
        old_start=10.0, old_end=14.0,
        old_source_start=1.0, old_source_end=5.0,
        new_start=7.0, new_end=14.0,
        new_source_start=-2.0, new_source_end=5.0,
    )
    cmd.redo()
    with DBSession(test_engine) as s:
        first = tuple(
            getattr(s.get(TimelineEntry, entry_id), field)
            for field in ("start_time", "end_time", "source_start", "source_end")
        )

    cmd.undo()
    cmd.redo()
    with DBSession(test_engine) as s:
        second = tuple(
            getattr(s.get(TimelineEntry, entry_id), field)
            for field in ("start_time", "end_time", "source_start", "source_end")
        )

    assert first == second
