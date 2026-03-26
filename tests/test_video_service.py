import json
from unittest.mock import patch, MagicMock

from services.video_service import VideoAnalyzer
from services.ingest_service import ingest_video


def test_video_probe(tmp_path):
    """Testet die probe-Methode mit gemocktem ffprobe."""
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"\x00" * 100)

    analyzer = VideoAnalyzer()

    fake_output = json.dumps({
        "streams": [{
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "codec_name": "h264",
        }]
    })

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = fake_output

    with patch("services.video_service.subprocess.run", return_value=mock_result):
        result = analyzer.probe(str(video_file))

    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["fps"] == 30.0
    assert result["codec"] == "h264"


def test_analyze_and_store_updates_db(tmp_path, project):
    """Testet, dass analyze_and_store die DB korrekt aktualisiert."""
    video_file = tmp_path / "db_test.mp4"
    video_file.write_bytes(b"\x00" * 100)

    clip = ingest_video(str(video_file))
    assert clip is not None

    analyzer = VideoAnalyzer()

    fake_probe = json.dumps({
        "streams": [{
            "width": 3840,
            "height": 2160,
            "r_frame_rate": "24000/1001",
            "codec_name": "hevc",
        }]
    })

    mock_probe = MagicMock()
    mock_probe.returncode = 0
    mock_probe.stdout = fake_probe

    proxy_dir = tmp_path / "proxies"
    proxy_dir.mkdir(parents=True, exist_ok=True)

    def fake_subprocess_run(cmd, **kwargs):
        """Simuliert FFmpeg: Probe liefert Metadaten, Proxy erzeugt Dummy-Datei."""
        if "ffprobe" in cmd[0]:
            return mock_probe
        # ffmpeg-Proxy-Befehl: Ausgabedatei (letzter Positionsarg) als Dummy erstellen
        output_path = next(
            (arg for arg in reversed(cmd) if not arg.startswith("-")), None
        )
        if output_path:
            from pathlib import Path
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"\x00" * 1024)
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 0
        mock_ffmpeg.stdout = ""
        mock_ffmpeg.stderr = ""
        return mock_ffmpeg

    with patch("services.video_service.subprocess.run", side_effect=fake_subprocess_run):
        with patch("services.video_service.PROXY_DIR", proxy_dir):
            result = analyzer.analyze_and_store(clip.id)

    assert result["width"] == 3840
    assert result["height"] == 2160
    assert result["codec"] == "hevc"
    assert abs(result["fps"] - 23.98) < 0.01

    # Prüfe DB
    from sqlalchemy.orm import Session
    from database import engine, VideoClip
    with Session(engine) as session:
        db_clip = session.get(VideoClip, clip.id)
        assert db_clip.width == 3840
        assert db_clip.codec == "hevc"
