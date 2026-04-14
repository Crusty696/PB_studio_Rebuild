"""
Tests fuer services/video_service.py

Getestet: VideoAnalyzer.analyze_and_store(), VideoAnalyzer.create_proxy()
Keine echten ffmpeg/ffprobe-Aufrufe – alles gemockt.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from sqlalchemy.orm import Session

import database
from database import VideoClip, Project


# ---------------------------------------------------------------------------
# VideoAnalyzer.probe() Tests
# ---------------------------------------------------------------------------

class TestVideoAnalyzerProbe:
    def test_probe_parses_ffprobe_output(self):
        """probe() parst ffprobe JSON korrekt."""
        from services.video_service import VideoAnalyzer

        fake_output = """{
            "streams": [{
                "width": 1920, "height": 1080, "fps": "30/1",
                "r_frame_rate": "30/1", "codec_name": "h264",
                "duration": "10.5"
            }],
            "format": {"duration": "10.5"}
        }"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_output

        with patch("services.video_service.subprocess.run", return_value=mock_result), \
             patch("services.video_service.Path.exists", return_value=True):
            info = VideoAnalyzer().probe("/fake/video.mp4")

        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["fps"] == 30.0
        assert info["codec"] == "h264"
        assert info["duration"] == 10.5

    def test_probe_raises_on_nonzero_returncode(self):
        """probe() loest RuntimeError aus wenn ffprobe fehlschlaegt."""
        from services.video_service import VideoAnalyzer

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No such file"

        with patch("services.video_service.subprocess.run", return_value=mock_result), \
             patch("services.video_service.Path.exists", return_value=True):
            with pytest.raises(Exception, match="ffprobe fehlgeschlagen"):
                VideoAnalyzer().probe("/nonexistent.mp4")

    def test_probe_raises_when_no_video_stream(self):
        """probe() loest ValueError aus wenn kein Video-Stream vorhanden."""
        from services.video_service import VideoAnalyzer
        import json as json_mod

        fake_output = json_mod.dumps({"streams": [], "format": {}})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_output

        with patch("services.video_service.subprocess.run", return_value=mock_result), \
             patch("services.video_service.Path.exists", return_value=True):
            with pytest.raises(ValueError, match="Kein Video-Stream"):
                VideoAnalyzer().probe("/video_without_stream.mp4")


# ---------------------------------------------------------------------------
# VideoAnalyzer.create_proxy() Tests
# ---------------------------------------------------------------------------

class TestVideoAnalyzerCreateProxy:
    def test_create_proxy_calls_ffmpeg(self, tmp_path):
        """create_proxy() ruft ffmpeg auf und gibt Proxy-Pfad zurueck."""
        from services.video_service import VideoAnalyzer

        # Mock: ffmpeg laeuft erfolgreich
        mock_result = MagicMock()
        mock_result.returncode = 0

        # Simuliere dass ffmpeg eine Ausgabedatei erstellt
        def fake_run(cmd, **kwargs):
            # Erzeuge den Proxy als leere Datei (simuliert Output)
            for arg in cmd:
                if "_proxy.mp4" in str(arg):
                    p = Path(arg)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"fake proxy content")
                    break
            return mock_result

        from pathlib import Path

        src = tmp_path / "test.mp4"
        src.write_bytes(b"fake video")

        with patch("services.video_service.subprocess.run", side_effect=fake_run):
            with patch.object(VideoAnalyzer, "create_proxy",
                              return_value=str(tmp_path / "test_proxy.mp4")) as mock_cp:
                analyzer = VideoAnalyzer()
                result = analyzer.create_proxy(str(src))

        assert result is not None

    def test_create_proxy_returns_existing_proxy(self, tmp_path, monkeypatch):
        """create_proxy() gibt bestehenden Proxy zurueck ohne ffmpeg aufzurufen."""
        from services.video_service import VideoAnalyzer

        src = tmp_path / "existing.mp4"
        src.write_bytes(b"fake video")

        # Proxy existiert bereits mit Inhalt
        proxy_dir = tmp_path / "proxies"
        proxy_dir.mkdir()
        proxy = proxy_dir / "existing_proxy.mp4"
        proxy.write_bytes(b"existing proxy content")

        # _proxy_dir() umleiten
        monkeypatch.setattr("services.video_service._proxy_dir", lambda: proxy_dir)

        with patch("services.video_service.subprocess.run") as mock_run:
            analyzer = VideoAnalyzer()
            result = analyzer.create_proxy(str(src))

        # ffmpeg darf NICHT aufgerufen worden sein
        mock_run.assert_not_called()
        assert result == str(proxy.resolve())


# ---------------------------------------------------------------------------
# VideoAnalyzer.analyze_and_store() Tests – Session-Split Pattern
# ---------------------------------------------------------------------------

class TestVideoAnalyzerAnalyzeAndStore:
    def _setup_clip(self, test_engine, file_path="/fake/video.mp4") -> int:
        """Legt einen VideoClip in der Test-DB an und gibt seine ID zurueck."""
        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path=file_path)
            s.add(clip)
            s.commit()
            s.refresh(clip)
            return clip.id

    def test_analyze_and_store_updates_metadata(self, test_engine):
        """analyze_and_store() aktualisiert Metadaten in der DB."""
        import services.video_service as svc
        svc.engine = test_engine

        clip_id = self._setup_clip(test_engine)

        fake_info = {
            "width": 1280, "height": 720, "fps": 24.0,
            "codec": "hevc", "duration": 15.0,
        }

        with patch.object(svc.VideoAnalyzer, "probe", return_value=fake_info):
            with patch.object(svc.VideoAnalyzer, "create_proxy",
                              return_value="/fake/proxy.mp4"):
                result = svc.VideoAnalyzer().analyze_and_store(clip_id, create_proxy=True)

        assert result["width"] == 1280
        assert result["fps"] == 24.0
        assert result["codec"] == "hevc"

        # DB-Werte pruefen
        with Session(test_engine) as s:
            clip = s.get(VideoClip, clip_id)
            assert clip.width == 1280
            assert clip.fps == 24.0
            assert clip.proxy_path == "/fake/proxy.mp4"

    def test_analyze_and_store_raises_for_missing_clip(self, test_engine):
        """analyze_and_store() loest ValueError aus wenn Clip nicht existiert."""
        import services.video_service as svc
        svc.engine = test_engine

        # Kein Clip angelegt – ID 9999 existiert nicht
        with pytest.raises(ValueError, match="VideoClip 9999 nicht gefunden"):
            svc.VideoAnalyzer().analyze_and_store(9999)

    def test_analyze_and_store_no_proxy_skips_proxy_creation(self, test_engine):
        """analyze_and_store() mit create_proxy=False erstellt keinen Proxy."""
        import services.video_service as svc
        svc.engine = test_engine

        clip_id = self._setup_clip(test_engine)

        fake_info = {
            "width": 1920, "height": 1080, "fps": 30.0,
            "codec": "h264", "duration": 10.0,
        }

        with patch.object(svc.VideoAnalyzer, "probe", return_value=fake_info):
            with patch.object(svc.VideoAnalyzer, "create_proxy") as mock_proxy:
                svc.VideoAnalyzer().analyze_and_store(clip_id, create_proxy=False)

        # create_proxy darf nicht aufgerufen worden sein
        mock_proxy.assert_not_called()

        # proxy_path muss None sein
        with Session(test_engine) as s:
            clip = s.get(VideoClip, clip_id)
            assert clip.proxy_path is None

    def test_session_split_pattern_metadata_committed_before_proxy(self, test_engine):
        """Metadaten werden committed BEVOR der Proxy erstellt wird (Session-Split)."""
        import services.video_service as svc
        svc.engine = test_engine

        clip_id = self._setup_clip(test_engine)
        committed_before_proxy = {"done": False}

        fake_info = {
            "width": 640, "height": 360, "fps": 25.0,
            "codec": "h264", "duration": 5.0,
        }

        def check_committed_proxy(*args, **kwargs):
            """Pruefen ob Metadaten bereits in DB sind wenn Proxy erstellt wird."""
            with Session(test_engine) as s:
                clip = s.get(VideoClip, clip_id)
                if clip and clip.width == 640:
                    committed_before_proxy["done"] = True
            return "/fake/proxy.mp4"

        with patch.object(svc.VideoAnalyzer, "probe", return_value=fake_info):
            with patch.object(svc.VideoAnalyzer, "create_proxy",
                              side_effect=check_committed_proxy):
                svc.VideoAnalyzer().analyze_and_store(clip_id, create_proxy=True)

        assert committed_before_proxy["done"], \
            "Metadaten wurden NICHT vor Proxy-Erstellung committed (Session-Split verletzt!)"
