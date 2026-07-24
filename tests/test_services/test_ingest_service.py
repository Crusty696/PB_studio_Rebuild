"""
Tests fuer services/ingest_service.py

Getestet: _file_meta(), ingest_audio(), ingest_video()
Keine echten Dateien, keine echten ffprobe-Aufrufe (alles gemockt).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

import database
from database import AudioTrack, VideoClip, Project


# ---------------------------------------------------------------------------
# _file_meta() Tests
# ---------------------------------------------------------------------------

class TestFileMeta:
    def test_file_meta_existing_file(self, tmp_path):
        """_file_meta gibt dict mit korrekten Schluesseln zurueck."""
        from services.ingest_service import _file_meta

        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake audio content")

        meta = _file_meta(audio_file)

        assert meta["file_path"] == str(audio_file.resolve())
        assert meta["title"] == "track"
        assert meta["extension"] == ".mp3"
        assert meta["size_bytes"] > 0

    def test_file_meta_raises_for_missing_file(self, tmp_path):
        """_file_meta loest FileNotFoundError aus wenn Datei fehlt."""
        from services.ingest_service import _file_meta

        missing = tmp_path / "nonexistent.mp3"

        with pytest.raises(FileNotFoundError, match="Datei nicht gefunden"):
            _file_meta(missing)

    @pytest.mark.parametrize("suffix,expected_ext", [
        (".MP3", ".mp3"),
        (".WAV", ".wav"),
        (".FLAC", ".flac"),
    ])
    def test_file_meta_normalizes_extension_to_lowercase(self, tmp_path, suffix, expected_ext):
        """Dateiendung wird in Kleinschreibung normalisiert."""
        from services.ingest_service import _file_meta

        f = tmp_path / f"file{suffix}"
        f.write_bytes(b"x")

        meta = _file_meta(f)
        assert meta["extension"] == expected_ext


# ---------------------------------------------------------------------------
# ingest_audio() Tests
# ---------------------------------------------------------------------------

class TestIngestAudio:
    def test_ingest_audio_creates_track_in_db(self, test_engine, tmp_path):
        """ingest_audio() legt einen AudioTrack in der DB an."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        audio_file = tmp_path / "mix.mp3"
        audio_file.write_bytes(b"fake mp3")

        result = svc.ingest_audio(str(audio_file), project_id=1)

        assert result is not None
        assert result.id is not None
        assert result.title == "mix"
        assert str(audio_file.resolve()) in result.file_path

    def test_ingest_audio_returns_none_for_duplicate(self, test_engine, tmp_path):
        """ingest_audio() gibt None zurueck wenn Datei bereits importiert."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        audio_file = tmp_path / "mix.mp3"
        audio_file.write_bytes(b"fake mp3")

        first = svc.ingest_audio(str(audio_file), project_id=1)
        assert first is not None

        second = svc.ingest_audio(str(audio_file), project_id=1)
        assert second is None

    def test_b345_ingest_audio_allows_same_file_in_second_project(self, test_engine, tmp_path):
        """B-345: Duplicate check muss project_id scopen."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add_all([
                Project(id=1, name="P1", path="."),
                Project(id=2, name="P2", path="."),
            ])
            s.commit()

        audio_file = tmp_path / "mix.mp3"
        audio_file.write_bytes(b"fake mp3")

        first = svc.ingest_audio(str(audio_file), project_id=1)
        second = svc.ingest_audio(str(audio_file), project_id=2)

        assert first is not None
        assert second is not None
        assert first.id != second.id
        assert second.project_id == 2

    def test_ingest_audio_raises_for_missing_file(self, test_engine):
        """ingest_audio() loest FileNotFoundError aus wenn Datei fehlt."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        with pytest.raises(FileNotFoundError):
            svc.ingest_audio("/nonexistent/path/file.mp3", project_id=1)

    def test_ingest_audio_reimport_after_soft_delete_undeletes(self, test_engine, tmp_path):
        """B-175: Re-Import einer soft-geloeschten Datei reaktiviert die Zeile
        (kein IntegrityError, kein stilles Skip)."""
        import datetime
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        audio_file = tmp_path / "mix.mp3"
        audio_file.write_bytes(b"fake mp3")

        first = svc.ingest_audio(str(audio_file), project_id=1)
        assert first is not None
        first_id = first.id

        # Soft-Delete simulieren
        with Session(test_engine) as s:
            track = s.get(AudioTrack, first_id)
            track.deleted_at = datetime.datetime.now()
            s.commit()

        # Re-Import: darf NICHT am UNIQUE-Constraint scheitern und soll die
        # gleiche Zeile reaktiviert zurueckliefern.
        reimported = svc.ingest_audio(str(audio_file), project_id=1)
        assert reimported is not None
        assert reimported.id == first_id

        with Session(test_engine) as s:
            track = s.get(AudioTrack, first_id)
            assert track.deleted_at is None
            # Es darf nur EINE Zeile fuer (project_id, file_path) existieren.
            count = (
                s.query(AudioTrack)
                .filter_by(project_id=1, file_path=str(audio_file.resolve()))
                .count()
            )
            assert count == 1


# ---------------------------------------------------------------------------
# ingest_video() Tests (mit Mock-ffprobe)
# ---------------------------------------------------------------------------

class TestIngestVideo:
    def _fake_probe(self) -> dict:
        return {
            "duration": 30.0,
            "width": 1920,
            "height": 1080,
            "fps": 25.0,
            "codec": "h264",
        }

    def test_ingest_video_creates_clip_in_db(self, test_engine, tmp_path):
        """ingest_video() legt VideoClip in DB an (ffprobe gemockt)."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"fake mp4")

        with patch.object(svc, "_probe_video_meta", return_value=self._fake_probe()):
            result = svc.ingest_video(str(video_file), project_id=1)

        assert result is not None
        assert result.id is not None
        assert result.width == 1920
        assert result.fps == 25.0
        assert result.codec == "h264"

    def test_ingest_video_returns_none_for_duplicate(self, test_engine, tmp_path):
        """ingest_video() gibt None zurueck bei doppeltem Import."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"fake mp4")

        with patch.object(svc, "_probe_video_meta", return_value=self._fake_probe()):
            first = svc.ingest_video(str(video_file), project_id=1)
            assert first is not None
            second = svc.ingest_video(str(video_file), project_id=1)
            assert second is None

    def test_b345_ingest_video_allows_same_file_in_second_project(self, test_engine, tmp_path):
        """B-345: Video duplicate check muss project_id scopen."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add_all([
                Project(id=1, name="P1", path="."),
                Project(id=2, name="P2", path="."),
            ])
            s.commit()

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"fake mp4")

        with patch.object(svc, "_probe_video_meta", return_value=self._fake_probe()):
            first = svc.ingest_video(str(video_file), project_id=1)
            second = svc.ingest_video(str(video_file), project_id=2)

        assert first is not None
        assert second is not None
        assert first.id != second.id
        assert second.project_id == 2

    def test_ingest_video_rejects_unreadable_file_on_probe_failure(self, test_engine, tmp_path):
        """B-701: leeres Probe-Ergebnis (korrupt/0-Byte/kein Video-Stream) wird
        sichtbar abgelehnt statt still als metadatenloser Clip importiert.

        (Ersetzt das alte Verhalten 'Clip auch bei fehlgeschlagenem ffprobe
        anlegen' — genau das war der stille Bad-Import aus B-701 Defekt 1.)"""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"fake mp4")

        with patch.object(svc, "_probe_video_meta", return_value={}):
            with pytest.raises(ValueError, match="unlesbar"):
                svc.ingest_video(str(video_file), project_id=1)

        with Session(test_engine) as s:
            assert s.query(VideoClip).count() == 0  # nichts still angelegt

    def test_ingest_video_raises_for_missing_file(self, test_engine):
        """ingest_video() loest FileNotFoundError aus wenn Datei fehlt."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        with pytest.raises(FileNotFoundError):
            svc.ingest_video("/nonexistent/video.mp4", project_id=1)

    def test_ingest_video_reimport_after_soft_delete_undeletes(self, test_engine, tmp_path):
        """B-175: Re-Import eines soft-geloeschten Videos reaktiviert die Zeile."""
        import datetime
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            s.add(Project(name="Default", path="."))
            s.commit()

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"fake mp4")

        with patch.object(svc, "_probe_video_meta", return_value=self._fake_probe()):
            first = svc.ingest_video(str(video_file), project_id=1)
            assert first is not None
            first_id = first.id

            with Session(test_engine) as s:
                clip = s.get(VideoClip, first_id)
                clip.deleted_at = datetime.datetime.now()
                s.commit()

            reimported = svc.ingest_video(str(video_file), project_id=1)
            assert reimported is not None
            assert reimported.id == first_id

        with Session(test_engine) as s:
            clip = s.get(VideoClip, first_id)
            assert clip.deleted_at is None
            count = (
                s.query(VideoClip)
                .filter_by(project_id=1, file_path=str(video_file.resolve()))
                .count()
            )
            assert count == 1


# ---------------------------------------------------------------------------
# get_all_audio / get_all_video Tests
# ---------------------------------------------------------------------------

class TestGetAllMedia:
    def test_get_all_audio_returns_list(self, test_engine):
        """get_all_audio() liefert eine Liste von dicts."""
        import services.ingest_service as svc
        svc.engine = test_engine

        # WICHTIG: project_id als Integer aus der Session extrahieren,
        # NICHT als SQLAlchemy-Objekt-Attribut nach Session-Close (DetachedInstanceError!)
        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id  # Integer sofort extrahieren

            s.add(AudioTrack(project_id=proj_id, file_path="/a.mp3", title="A"))
            s.commit()

        result = svc.get_all_audio(project_id=proj_id)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_get_all_video_returns_list(self, test_engine):
        """get_all_video() liefert eine Liste von dicts."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id  # Integer sofort extrahieren

            s.add(VideoClip(project_id=proj_id, file_path="/v.mp4", width=1920, height=1080))
            s.commit()

        result = svc.get_all_video(project_id=proj_id)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["resolution"] == "1920x1080"

    def test_get_all_video_backfills_metadata_analysis_percent(self, test_engine, monkeypatch):
        """Vorhandene Metadaten duerfen in der Medienliste nicht als 0% erscheinen."""
        import database
        import services.ingest_service as svc
        from services import analysis_status_service

        svc.engine = test_engine
        monkeypatch.setattr(analysis_status_service, "nullpool_session", database.nullpool_session)

        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id

            s.add(
                VideoClip(
                    project_id=proj_id,
                    file_path="/v.mp4",
                    duration=10.0,
                    width=1920,
                    height=1080,
                    fps=30.0,
                    codec="h264",
                )
            )
            s.commit()

        result = svc.get_all_video(project_id=proj_id)

        assert len(result) == 1
        assert result[0]["analysis_percent"] > 0.0

    def test_get_all_audio_empty_project(self, test_engine):
        """get_all_audio() liefert leere Liste fuer Projekt ohne Tracks."""
        import services.ingest_service as svc
        svc.engine = test_engine

        with Session(test_engine) as s:
            proj = Project(name="Leer", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id

        result = svc.get_all_audio(project_id=proj_id)
        assert result == []


# ---------------------------------------------------------------------------
# B-280: Import auf leerer DB / ohne aktives Projekt
# ---------------------------------------------------------------------------

class TestResolveProjectIdForIngest:
    def test_explicit_project_id_passthrough(self):
        """Expliziter project_id wird unveraendert durchgereicht."""
        from services.ingest_service import _resolve_project_id_for_ingest
        assert _resolve_project_id_for_ingest(7) == 7

    def test_no_active_project_raises_clear_error(self):
        """B-280: Kein aktives Projekt -> klare ValueError, KEIN =1-Fallback."""
        import services.ingest_service as svc

        with patch("database.session.get_active_project_id", return_value=None):
            with pytest.raises(ValueError, match="Kein aktives Projekt"):
                svc._resolve_project_id_for_ingest(None)

    def test_active_project_resolved(self):
        """Aktives Projekt vorhanden -> dessen ID wird zurueckgegeben."""
        import services.ingest_service as svc

        with patch("database.session.get_active_project_id", return_value=42):
            assert svc._resolve_project_id_for_ingest(None) == 42

    def test_ingest_audio_no_active_project_blocks_import(self, test_engine, tmp_path):
        """B-280: ingest_audio(project_id=None) auf leerer DB faellt NICHT auf
        project_id=1 zurueck, sondern blockt mit klarer Meldung."""
        import services.ingest_service as svc
        svc.engine = test_engine

        audio_file = tmp_path / "mix.mp3"
        audio_file.write_bytes(b"fake mp3")

        with patch("database.session.get_active_project_id", return_value=None):
            with pytest.raises(ValueError, match="Kein aktives Projekt"):
                svc.ingest_audio(str(audio_file), project_id=None)
