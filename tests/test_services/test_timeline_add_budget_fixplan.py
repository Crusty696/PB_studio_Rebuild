"""Fixplan 2026-07-07 Schritt 7b: Audio-Laengen-Budget fuer den Timeline-Add-Pfad.

Fehlerbild (User-Test 2026-07-07 02:43): "Zur Timeline hinzufuegen" appendete
2x alle 39 markierten Clips ungebremst -> 137 Clips / 1003 s Timeline bei
308 s Audio. plan_video_timeline_add() ist der zentrale Budget-Planer fuer
UI-Button UND Chat-Action.
"""
import pytest
from sqlalchemy.orm import Session

from database.models import AudioTrack, Project, TimelineEntry, VideoClip
from services.timeline_service import plan_video_timeline_add


@pytest.fixture()
def project_with_media(test_engine):
    """Projekt mit 60s-Audio + 10 Videos je 8s; Timeline leer."""
    with Session(test_engine) as s:
        p = Project(name="budget-test", path="/tmp/budget-test")
        s.add(p)
        s.flush()
        s.add(AudioTrack(project_id=p.id, title="track", duration=60.0,
                         file_path="/tmp/a.mp3"))
        s.flush()
        vids = []
        for i in range(10):
            v = VideoClip(project_id=p.id, file_path=f"/tmp/v{i}.mp4",
                          duration=8.0)
            s.add(v)
            s.flush()
            vids.append(v.id)
        audio_id = s.query(AudioTrack).first().id
        s.commit()
        return p.id, audio_id, vids


def _add_audio_to_timeline(engine, project_id, audio_id, duration=60.0):
    with Session(engine) as s:
        s.add(TimelineEntry(project_id=project_id, track="audio",
                            media_id=audio_id, start_time=0.0,
                            end_time=duration, lane=0))
        s.commit()


class TestBudget:
    def test_bulk_capped_at_audio_length(self, test_engine, project_with_media):
        pid, audio_id, vids = project_with_media
        _add_audio_to_timeline(test_engine, pid, audio_id)
        plan = plan_video_timeline_add(pid, vids)
        # 60s Budget / 8s Clips -> 8 Clips (Start des 8. bei 56 < 60), Rest gekappt
        assert plan["blocked_reason"] is None
        assert plan["budget"] == 60.0
        assert len(plan["accepted"]) == 8
        assert len(plan["skipped_budget"]) == 2
        starts = [c["start_time"] for c in plan["accepted"]]
        assert starts == [i * 8.0 for i in range(8)]

    def test_bulk_without_audio_blocked(self, test_engine, project_with_media):
        pid, _audio_id, vids = project_with_media
        plan = plan_video_timeline_add(pid, vids)
        assert plan["blocked_reason"] is not None
        assert plan["accepted"] == []

    def test_audio_hint_used_when_timeline_empty(self, test_engine, project_with_media):
        """Audio wird im selben Vorgang mit-markiert -> dessen Dauer = Budget."""
        pid, audio_id, vids = project_with_media
        plan = plan_video_timeline_add(pid, vids, audio_id_hint=audio_id)
        assert plan["blocked_reason"] is None
        assert plan["budget"] == 60.0
        assert len(plan["accepted"]) == 8

    def test_single_add_without_audio_allowed(self, test_engine, project_with_media):
        pid, _audio_id, vids = project_with_media
        plan = plan_video_timeline_add(pid, [vids[0]])
        assert plan["blocked_reason"] is None
        assert len(plan["accepted"]) == 1

    def test_single_add_rejected_when_track_full(self, test_engine, project_with_media):
        pid, audio_id, vids = project_with_media
        _add_audio_to_timeline(test_engine, pid, audio_id)
        with Session(test_engine) as s:
            s.add(TimelineEntry(project_id=pid, track="video",
                                media_id=vids[0], start_time=0.0,
                                end_time=60.0, lane=0))
            s.commit()
        plan = plan_video_timeline_add(pid, [vids[1]], allow_duplicates=True)
        assert plan["accepted"] == []
        assert plan["skipped_budget"] == [vids[1]]


class TestDedup:
    def test_bulk_skips_clips_already_on_track(self, test_engine, project_with_media):
        pid, audio_id, vids = project_with_media
        _add_audio_to_timeline(test_engine, pid, audio_id)
        with Session(test_engine) as s:
            s.add(TimelineEntry(project_id=pid, track="video",
                                media_id=vids[0], start_time=0.0,
                                end_time=8.0, lane=0))
            s.commit()
        plan = plan_video_timeline_add(pid, vids)
        assert vids[0] in plan["skipped_duplicate"]
        accepted_ids = [c["media_id"] for c in plan["accepted"]]
        assert vids[0] not in accepted_ids
        # Anfuegen beginnt am Ende der bestehenden Spur (8.0s)
        assert plan["accepted"][0]["start_time"] == 8.0

    def test_bulk_dedups_within_request(self, test_engine, project_with_media):
        pid, audio_id, vids = project_with_media
        _add_audio_to_timeline(test_engine, pid, audio_id)
        plan = plan_video_timeline_add(pid, [vids[0], vids[0], vids[1]])
        accepted_ids = [c["media_id"] for c in plan["accepted"]]
        assert accepted_ids == [vids[0], vids[1]]
        assert plan["skipped_duplicate"] == [vids[0]]

    def test_single_add_may_duplicate(self, test_engine, project_with_media):
        pid, audio_id, vids = project_with_media
        _add_audio_to_timeline(test_engine, pid, audio_id)
        with Session(test_engine) as s:
            s.add(TimelineEntry(project_id=pid, track="video",
                                media_id=vids[0], start_time=0.0,
                                end_time=8.0, lane=0))
            s.commit()
        plan = plan_video_timeline_add(pid, [vids[0]])
        assert [c["media_id"] for c in plan["accepted"]] == [vids[0]]
        assert plan["skipped_duplicate"] == []


def test_empty_request_is_noop(test_engine, project_with_media):
    pid, _a, _v = project_with_media
    plan = plan_video_timeline_add(pid, [])
    assert plan["accepted"] == [] and plan["blocked_reason"] is None
