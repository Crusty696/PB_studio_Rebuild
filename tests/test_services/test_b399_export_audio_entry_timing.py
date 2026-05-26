from __future__ import annotations

from types import SimpleNamespace

from tests.test_services.test_b395_export_source_range_validation import _Query, _Session


def test_b399_export_prepares_audio_entry_trim_and_timeline_offset(tmp_path, monkeypatch):
    from services import export_service as exp

    entries = [
        SimpleNamespace(
            id=40,
            project_id=1,
            track="video",
            media_id=1,
            start_time=0.0,
            end_time=20.0,
            source_start=0.0,
            source_end=20.0,
            crossfade_duration=0.0,
            brightness=0.0,
            contrast=1.0,
        ),
        SimpleNamespace(
            id=41,
            project_id=1,
            track="audio",
            media_id=2,
            start_time=10.0,
            end_time=20.0,
            source_start=3.0,
            source_end=13.0,
        ),
    ]
    clips = [SimpleNamespace(id=1, file_path="clip.mp4", duration=30.0)]
    tracks = [SimpleNamespace(id=2, file_path="track.wav", duration=30.0)]

    class _ExportSession(_Session):
        def query(self, model):
            if model is exp.AudioTrack:
                return self._audio_query
            return super().query(model)

    session = _ExportSession(entries, clips)
    session._audio_query = _Query(tracks)

    prepared_cmds: list[list[str]] = []
    exported_audio_paths: list[str | None] = []

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: session)
    monkeypatch.setattr(exp, "_video_encode_args", lambda: ["-c:v", "libx264"])
    monkeypatch.setattr(exp, "_run_ffmpeg", lambda cmd, **kwargs: prepared_cmds.append(cmd))
    monkeypatch.setattr(
        exp,
        "_export_optimized_concat",
        lambda video_segments, audio_path, *args, **kwargs: exported_audio_paths.append(audio_path) or "out.mp4",
    )

    exp.export_timeline(project_id=1, output_name="safe.mp4")

    assert exported_audio_paths and exported_audio_paths[0] != "track.wav"
    assert prepared_cmds, "audio trim/offset preparation ffmpeg was not called"
    cmd = prepared_cmds[0]
    assert "-ss" in cmd and cmd[cmd.index("-ss") + 1] == "3.000"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "10.000"
    assert "-af" in cmd and "adelay=10000:all=1" in cmd[cmd.index("-af") + 1]
