from types import SimpleNamespace


class _DetachedSensitiveClip:
    def __init__(self) -> None:
        self.active = False
        self._values = {
            "duration": 12.5,
            "width": 1920,
            "height": 1080,
            "fps": 25.0,
            "codec": "h264",
        }

    def _get(self, key: str):
        if not self.active:
            raise RuntimeError(f"detached access: {key}")
        return self._values[key]

    @property
    def duration(self):
        return self._get("duration")

    @property
    def width(self):
        return self._get("width")

    @property
    def height(self):
        return self._get("height")

    @property
    def fps(self):
        return self._get("fps")

    @property
    def codec(self):
        return self._get("codec")


class _FakeSession:
    def __init__(self, row: _DetachedSensitiveClip) -> None:
        self.row = row

    def __enter__(self):
        self.row.active = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.row.active = False

    def get(self, _model, _clip_id):
        return self.row

    def query(self, _model):
        return self

    def filter(self, *_criteria):
        return self

    def first(self):
        return self.row


def test_pipeline_metadata_snapshot_before_session_close(monkeypatch, qapp) -> None:
    from services import analysis_status_service
    from workers.video import VideoAnalysisPipelineWorker

    row = _DetachedSensitiveClip()
    done_calls: list[tuple[str, int, str, dict]] = []

    monkeypatch.setattr("database.nullpool_session", lambda: _FakeSession(row))
    monkeypatch.setattr("services.model_warmup.is_siglip_cached", lambda: (True, []))
    monkeypatch.setattr("services.model_warmup.warmup_siglip", lambda progress_cb=None: None)
    monkeypatch.setattr(
        "services.video_analysis_service.run_full_pipeline",
        lambda **_kwargs: SimpleNamespace(scenes=[], embeddings_stored=0),
    )
    monkeypatch.setattr(
        "services.video_analysis_service.run_deferred_captioning",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        analysis_status_service,
        "mark_done",
        lambda media_type, media_id, step_key, summary: done_calls.append(
            (media_type, media_id, step_key, summary)
        ),
    )
    monkeypatch.setattr(
        analysis_status_service,
        "mark_started",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mark_started called")),
    )

    worker = VideoAnalysisPipelineWorker(batch=[(42, "C:/media/clip.mp4", "clip")])
    worker.run()

    assert done_calls == [
        (
            "video",
            42,
            "metadata_extract",
            {
                "duration": 12.5,
                "resolution": "1920x1080",
                "fps": 25.0,
                "codec": "h264",
            },
        )
    ]
