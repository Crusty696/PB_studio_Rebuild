"""B-806: "Zur Timeline hinzufuegen" blockte bei nicht-analysiertem Audio.

Fehlerbild (Live-Verify Runde 6, 2026-08-12, Projekt Runde6-S2-RaceA):
Audio-Checkbox sichtbar gesetzt, trotzdem
``[Timeline] Nicht hinzugefuegt: Kein Audio-Track als Laengen-Referenz
vorhanden.``

Belegte Ursache (NICHT die Checkbox — die liefert die ID korrekt):
* ``ingest_audio()`` legte ``AudioTrack`` ohne ``duration`` an (anders als
  ``ingest_video()``, das per ffprobe misst) -> ``audio_tracks.duration IS
  NULL`` bis die BPM-/Wellenform-Analyse lief.
  DB-Beleg: Runde6-S2-RaceA -> ``(1, 'lv3_maceo_full', None, 1)``.
* ``plan_video_timeline_add()`` leitete daraus "kein Audio-Track vorhanden"
  ab und blockte den Bulk-Add — obwohl der Track existiert, markiert war und
  sogar schon auf der Timeline lag.

Die Meldung war zusaetzlich sachlich falsch und hat mehrere B-796-Testlaeufe
als "korrekte Validierung" fehlinterpretiert werden lassen.
"""
import pytest
from sqlalchemy.orm import Session

from database.models import AudioTrack, Project, TimelineEntry, VideoClip
from services.timeline_service import plan_video_timeline_add


@pytest.fixture()
def unanalysed_audio_project(test_engine, tmp_path):
    """Projekt wie nach frischem Import: Audio ohne ``duration``, 10 Videos."""
    audio_file = tmp_path / "lv3_maceo_full.mp3"
    audio_file.write_bytes(b"\x00" * 16)
    with Session(test_engine) as s:
        p = Project(name="b806", path=str(tmp_path))
        s.add(p)
        s.flush()
        track = AudioTrack(project_id=p.id, title="lv3_maceo_full",
                           duration=None, file_path=str(audio_file))
        s.add(track)
        s.flush()
        vids = []
        for i in range(10):
            v = VideoClip(project_id=p.id, file_path=f"/tmp/v{i}.mp4",
                          duration=8.0)
            s.add(v)
            s.flush()
            vids.append(v.id)
        pid, aid = p.id, track.id
        s.commit()
    return pid, aid, vids, str(audio_file)


def _patch_probe(monkeypatch, value):
    import services.ffmpeg_utils as fu
    monkeypatch.setattr(fu, "probe_duration",
                        lambda path, fallback=0.0, **kw: value)


class TestPlanUsesRealAudioLength:
    def test_hint_with_null_duration_is_not_blocked(
        self, test_engine, unanalysed_audio_project, monkeypatch
    ):
        """Kern-Repro: markiertes, un-analysiertes Audio -> darf nicht blocken."""
        pid, aid, vids, _path = unanalysed_audio_project
        _patch_probe(monkeypatch, 60.0)

        plan = plan_video_timeline_add(pid, vids, audio_id_hint=aid)

        assert plan["blocked_reason"] is None
        assert plan["budget"] == 60.0
        assert len(plan["accepted"]) == 8

    def test_timeline_audio_with_null_duration_is_not_blocked(
        self, test_engine, unanalysed_audio_project, monkeypatch
    ):
        """Gleicher Fall ueber die Timeline-Referenz statt ueber den Hint."""
        pid, aid, vids, _path = unanalysed_audio_project
        with Session(test_engine) as s:
            s.add(TimelineEntry(project_id=pid, track="audio", media_id=aid,
                                start_time=0.0, end_time=30.0, lane=0))
            s.commit()
        _patch_probe(monkeypatch, 60.0)

        plan = plan_video_timeline_add(pid, vids)

        assert plan["blocked_reason"] is None
        # 60.0 aus der Datei — NICHT die 30.0-Notdauer des Timeline-Eintrags
        # (die stammt aus dem ``or 30.0``-Fallback des Add-Workers).
        assert plan["budget"] == 60.0

    def test_probed_duration_is_persisted(
        self, test_engine, unanalysed_audio_project, monkeypatch
    ):
        """Einmal gemessen = dauerhaft bekannt (heilt Alt-Projekte)."""
        pid, aid, vids, _path = unanalysed_audio_project
        _patch_probe(monkeypatch, 60.0)

        plan_video_timeline_add(pid, vids, audio_id_hint=aid)

        with Session(test_engine) as s:
            assert s.get(AudioTrack, aid).duration == 60.0

    def test_message_is_truthful_when_length_unmeasurable(
        self, test_engine, unanalysed_audio_project, monkeypatch
    ):
        """ffprobe liefert nichts -> blocken ist ok, luegen nicht."""
        pid, aid, vids, _path = unanalysed_audio_project
        _patch_probe(monkeypatch, 0.0)

        plan = plan_video_timeline_add(pid, vids, audio_id_hint=aid)

        reason = plan["blocked_reason"]
        assert reason is not None
        assert "Kein Audio-Track als Laengen-Referenz vorhanden" not in reason
        assert "lv3_maceo_full" in reason

    def test_no_audio_at_all_still_blocks_with_old_message(
        self, test_engine, unanalysed_audio_project
    ):
        """Ohne jede Audio-Referenz bleibt die bisherige Meldung korrekt."""
        pid, _aid, vids, _path = unanalysed_audio_project
        plan = plan_video_timeline_add(pid, vids)
        assert "Kein Audio-Track als Laengen-Referenz vorhanden" in \
            plan["blocked_reason"]


class TestIngestStoresDuration:
    def test_ingest_audio_measures_duration(self, test_engine, tmp_path,
                                            monkeypatch):
        """Wurzel: Import muss die Laenge kennen (wie ingest_video)."""
        from services import ingest_service

        audio_file = tmp_path / "neu.mp3"
        audio_file.write_bytes(b"\x00" * 16)
        with Session(test_engine) as s:
            p = Project(name="b806-ingest", path=str(tmp_path))
            s.add(p)
            s.commit()
            pid = p.id
        _patch_probe(monkeypatch, 123.5)

        track = ingest_service.ingest_audio(str(audio_file), project_id=pid)

        assert track is not None
        with Session(test_engine) as s:
            assert s.get(AudioTrack, track.id).duration == 123.5
