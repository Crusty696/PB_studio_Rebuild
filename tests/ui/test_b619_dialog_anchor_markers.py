"""B-619 Folge: Timeline rendert persistierte Dialog-Anker als Marker.

Belegt, dass die Lade-Methode ``InteractiveTimeline._load_dialog_anchors``
ausschliesslich ``AudioVideoAnchor``-Rows mit ``anchor_type="dialog"`` des
aktiven PROJEKTS aus der DB holt (B-634: projekt-weit statt track-scoped, robust
gegen leeres audio_map beim Projekt-Oeffnen) und pro Anker ein Marker-Datum erzeugt.

Deterministischer Daten-/Positions-Test (kein echtes Qt-Rendering) — laeuft
offscreen ueber die ``qapp``-Fixture.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import ui.timeline as timeline_module
from database import AudioTrack, AudioVideoAnchor, Project, VideoClip
from ui.timeline import InteractiveTimeline, PIXELS_PER_SECOND


def test_load_dialog_anchors_reads_only_dialog_rows_and_builds_markers(
    qapp, test_engine, monkeypatch
):
    # ui.timeline bindet `engine` beim Import — Test-Engine dort patchen,
    # damit _load_dialog_anchors die In-Memory-DB nutzt.
    monkeypatch.setattr(timeline_module, "engine", test_engine)

    with Session(test_engine) as session:
        project = Project(name="B619", path="/tmp/b619")
        session.add(project)
        session.flush()
        track = AudioTrack(
            project_id=project.id, file_path="/tmp/a.mp3", title="A", duration=180.0
        )
        other_track = AudioTrack(
            project_id=project.id, file_path="/tmp/b.mp3", title="B", duration=90.0
        )
        clip = VideoClip(
            project_id=project.id, file_path="/tmp/v.mp4", duration=10.0,
            width=1920, height=1080, fps=30.0, codec="h264",
        )
        session.add_all([track, other_track, clip])
        session.flush()

        dialog_times = [30.0, 5.0, 12.5]  # bewusst unsortiert
        for t in dialog_times:
            session.add(AudioVideoAnchor(
                audio_track_id=track.id, video_clip_id=clip.id,
                audio_time=t, video_time=0.0, anchor_type="dialog",
            ))
        # anchor_type="beat" MUSS ignoriert werden (kein Dialog-Anker):
        session.add(AudioVideoAnchor(
            audio_track_id=track.id, video_clip_id=clip.id,
            audio_time=99.0, video_time=0.0, anchor_type="beat",
        ))
        # B-634: Dialog-Anker eines ANDEREN Tracks im SELBEN Projekt taucht jetzt
        # AUCH auf (projekt-weite Ladung). Nur anchor_type="beat" bleibt aussen vor.
        session.add(AudioVideoAnchor(
            audio_track_id=other_track.id, video_clip_id=clip.id,
            audio_time=77.0, video_time=0.0, anchor_type="dialog",
        ))
        session.commit()
        track_id = track.id

    timeline = InteractiveTimeline()
    try:
        times = timeline._load_dialog_anchors([track_id])

        # B-634 projekt-weit: alle Dialog-Anker des Projekts (track + other_track),
        # sortiert; anchor_type="beat" (99.0) bleibt ausgeschlossen.
        assert times == [5.0, 12.5, 30.0, 77.0]

        # set_dialog_anchor_markers -> pro Anker genau ein Marker-Datum.
        timeline.set_dialog_anchor_markers(times)
        assert timeline._dialog_anchor_times == [5.0, 12.5, 30.0, 77.0]
        assert timeline._dialog_anchor_markers_item._dialog_times == [5.0, 12.5, 30.0, 77.0]
        assert len(timeline._dialog_anchor_markers_item._dialog_times) == len(times)

        # Zeit->x-Umrechnung identisch zu Beats (t * PIXELS_PER_SECOND):
        expected_x = [t * PIXELS_PER_SECOND for t in times]
        actual_x = [t * PIXELS_PER_SECOND
                    for t in timeline._dialog_anchor_markers_item._dialog_times]
        assert actual_x == expected_x
    finally:
        timeline.deleteLater()


def test_load_dialog_anchors_empty_for_no_tracks(qapp, test_engine, monkeypatch):
    monkeypatch.setattr(timeline_module, "engine", test_engine)
    timeline = InteractiveTimeline()
    try:
        assert timeline._load_dialog_anchors([]) == []
        assert timeline._load_dialog_anchors(None) == []
    finally:
        timeline.deleteLater()
