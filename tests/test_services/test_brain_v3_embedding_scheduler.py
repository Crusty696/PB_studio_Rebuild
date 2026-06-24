"""Tests fuer EmbeddingScheduler (Phase 2 App-Sync).

Mockt Embedder-Factory damit kein torch/CUDA noetig ist.
Erfordert PySide6 fuer QThread/Signals.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from services.brain_v3.embedding_scheduler import (
    EmbeddingScheduler,
    EmbeddingTask,
    reset_default_scheduler_for_tests,
)
from services.brain_v3.gpu_serializer import (
    GpuSerializer,
    reset_default_serializer_for_tests,
)
from services.brain_v3.storage.embedding_cache import EmbeddingCache


@pytest.fixture(scope="module")
def qt_app():
    # QApplication ist Subklasse von QCoreApplication. Wenn schon eine
    # QCoreApplication existiert, bleibt sie aktiv. Sonst neue QApplication
    # damit Phase-5-Widget-Tests im selben Prozess kompatibel sind.
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    reset_default_serializer_for_tests()
    reset_default_scheduler_for_tests()
    yield tmp_path
    reset_default_scheduler_for_tests()
    reset_default_serializer_for_tests()


def _fake_embedder(task, progress_cb, serializer):
    progress_cb(0.5, "fake")
    return {
        "embedding": np.zeros(8, dtype=np.float32),
        "model_name": "fake/model",
        "model_version": "0.0",
    }


def _spin_qt(app, ms: int = 200) -> None:
    """Verarbeitet Qt-Events fuer ms Millisekunden."""
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)


def test_start_and_stop(qt_app, isolated_appdata):
    scheduler = EmbeddingScheduler(
        n_workers=1, embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    scheduler.start()
    assert scheduler.is_running()
    ok = scheduler.request_stop(timeout_ms=3000)
    assert ok
    assert not scheduler.is_running()


def test_submit_path_with_fake_embedder(qt_app, isolated_appdata):
    cache = EmbeddingCache()
    scheduler = EmbeddingScheduler(
        n_workers=1, cache=cache, embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    scheduler.start()
    try:
        media_hash = "f" * 64
        # source_path muss nicht existieren — fake-embedder ignoriert ihn
        job_id = scheduler.submit_path(
            media_hash=media_hash,
            source_path=isolated_appdata / "fake_audio.wav",
            media_type="audio",
        )
        assert job_id is not None
        assert isinstance(job_id, str)

        # warte bis Job verarbeitet
        deadline = time.time() + 5.0
        while time.time() < deadline:
            entry = cache.lookup(media_hash, "fake/model", "0.0")
            if entry is not None:
                break
            _spin_qt(qt_app, 50)
        else:
            pytest.fail("Job wurde nicht innerhalb von 5s verarbeitet")

        assert entry.media_hash == media_hash
        assert entry.media_type == "audio"
        assert entry.embedding_path.exists()
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_submit_path_emits_job_progress_signal(qt_app, isolated_appdata):
    cache = EmbeddingCache()
    scheduler = EmbeddingScheduler(
        n_workers=1, cache=cache, embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    progress_events: list[tuple[str, str, float, str]] = []
    scheduler.job_progress.connect(
        lambda job_id, status, progress, message: progress_events.append(
            (job_id, status, progress, message)
        )
    )
    scheduler.start()
    try:
        media_hash = "e" * 64
        job_id = scheduler.submit_path(
            media_hash=media_hash,
            source_path=isolated_appdata / "fake_video.mp4",
            media_type="video",
        )
        assert job_id is not None

        deadline = time.time() + 5.0
        while time.time() < deadline:
            if any(status == "done" for _jid, status, _progress, _msg in progress_events):
                break
            _spin_qt(qt_app, 50)
        else:
            pytest.fail("job_progress hat kein done-Signal geliefert")

        statuses = [status for _jid, status, _progress, _msg in progress_events]
        assert "pending" in statuses
        assert "running" in statuses
        assert "done" in statuses
        assert any(progress >= 0.5 for _jid, _status, progress, _msg in progress_events)
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_submit_path_does_not_skip_other_model_variant(qt_app, isolated_appdata):
    cache = EmbeddingCache()
    media_hash = "a" * 64
    cache.store(
        media_hash=media_hash, media_type="audio",
        embedding=np.zeros(8, dtype=np.float32),
        model_name="cached/model", model_version="1.0",
    )
    scheduler = EmbeddingScheduler(
        n_workers=1, cache=cache, embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    scheduler.start()
    try:
        skipped_signals = []
        scheduler.job_skipped.connect(lambda h, r: skipped_signals.append((h, r)))
        job_id = scheduler.submit_path(
            media_hash=media_hash,
            source_path=isolated_appdata / "any.wav",
            media_type="audio",
        )
        assert job_id is not None

        deadline = time.time() + 5.0
        while time.time() < deadline:
            entry = cache.lookup(media_hash, "fake/model", "0.0")
            if entry is not None:
                break
            _spin_qt(qt_app, 50)
        else:
            pytest.fail("Andere Modellvariante wurde nicht verarbeitet")

        assert skipped_signals == []
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_invalid_video_metadata_skips_instead_of_failing(qt_app, isolated_appdata):
    """B-279: ein Video mit ungueltigen Metadaten (.stem.mp4, frames=-1) wird
    als sauberer Skip-mit-Grund behandelt, nicht als fehlgeschlagener Job."""
    from services.brain_v3.video.video_embedder import InvalidVideoError

    def _bad_video_embedder(task, progress_cb, serializer):
        raise InvalidVideoError("Ungueltige Video-Metadaten: fps=1.0 frames=-1")

    cache = EmbeddingCache()
    scheduler = EmbeddingScheduler(
        n_workers=1, cache=cache, embedder_factory=_bad_video_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    skipped: list[tuple[str, str]] = []
    statuses: list[str] = []
    scheduler.job_skipped.connect(lambda h, r: skipped.append((h, r)))
    scheduler.job_progress.connect(
        lambda jid, status, p, m: statuses.append(status)
    )
    scheduler.start()
    try:
        media_hash = "d" * 64
        job_id = scheduler.submit_path(
            media_hash=media_hash,
            source_path=isolated_appdata / "test.stem.mp4",
            media_type="video",
        )
        assert job_id is not None

        deadline = time.time() + 5.0
        while time.time() < deadline:
            if skipped:
                break
            _spin_qt(qt_app, 50)
        else:
            pytest.fail("job_skipped wurde nicht emittiert")

        assert skipped[0][0] == media_hash
        assert "frames=-1" in skipped[0][1]
        # B-279: der Job darf NICHT als failed enden.
        _spin_qt(qt_app, 150)
        assert "failed" not in statuses
        assert "done" in statuses
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_failed_job_emits_error_text(qt_app, isolated_appdata):
    """B-567 Rest: ein fehlgeschlagener Embedding-Job muss status=='failed'
    UND den Fehlertext ueber das job_progress-Signal liefern (5. Arg `error`).
    Vorher wurde der Fehlertext in der Bridge verworfen -> stummer Pfad."""
    def _raising_embedder(task, progress_cb, serializer):
        raise RuntimeError("kaputter embedder xyz")

    scheduler = EmbeddingScheduler(
        n_workers=1, embedder_factory=_raising_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    events: list[tuple[str, str]] = []  # (status, error)
    scheduler.job_progress.connect(
        lambda jid, status, p, m, error="": events.append((status, error))
    )
    scheduler.start()
    try:
        job_id = scheduler.submit_path(
            media_hash="f" * 64,
            source_path=isolated_appdata / "broken.mp4",
            media_type="video",
        )
        assert job_id is not None

        deadline = time.time() + 5.0
        while time.time() < deadline:
            if any(status == "failed" for status, _err in events):
                break
            _spin_qt(qt_app, 50)
        else:
            pytest.fail("job_progress hat kein failed-Signal geliefert")

        failed = [err for status, err in events if status == "failed"]
        assert failed, "kein failed-Event"
        assert "kaputter embedder xyz" in failed[-1], (
            f"Fehlertext nicht durchgereicht, war: {failed[-1]!r}"
        )
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_submit_raises_when_not_started(qt_app, isolated_appdata):
    scheduler = EmbeddingScheduler(
        n_workers=1, embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    with pytest.raises(RuntimeError, match="nicht gestartet"):
        scheduler.submit_path(
            media_hash="0" * 64, source_path=Path("x.wav"), media_type="audio",
        )


def test_b554_default_factory_reuses_video_embedder(monkeypatch):
    """B-554: _default_embedder_factory darf die Embedder-Instanz NICHT pro Clip
    neu erzeugen — sonst wird das siglip2-Modell pro Clip neu geladen
    (from_pretrained + to(cuda), Stack-belegt). Ueber mehrere Clips darf nur
    EINE Instanz entstehen (Modell wird einmal geladen)."""
    from types import SimpleNamespace

    import services.brain_v3.video.video_embedder as ve
    from services.brain_v3 import embedding_scheduler as sched

    class _CountingEmbedder:
        instances = 0

        def __init__(self, serializer=None):
            type(self).instances += 1

        def embed_clip(self, source_path, video_hash):
            return SimpleNamespace(clip_embedding=np.zeros(8, dtype=np.float32))

        def unload(self):
            pass

    sched._reset_embedder_cache(unload=False)
    monkeypatch.setattr(ve, "Siglip2VideoEmbedder", _CountingEmbedder)
    monkeypatch.setattr(ve, "SIGLIP2_MODEL_ID", "fake/siglip2")
    monkeypatch.setattr(ve, "SIGLIP2_MODEL_VERSION", "0.0")
    _CountingEmbedder.instances = 0
    try:
        for h in ("11", "22", "33"):
            task = EmbeddingTask(
                media_hash=h * 32, media_type="video",
                source_path=Path(f"{h}.mp4"),
            )
            payload = sched._default_embedder_factory(
                task, lambda p, m: None,
                GpuSerializer(empty_cache_on_release=False),
            )
            assert isinstance(payload["embedding"], np.ndarray)
        assert _CountingEmbedder.instances == 1, (
            f"Embedder {_CountingEmbedder.instances}x erzeugt (pro Clip neu) "
            "statt wiederverwendet"
        )
    finally:
        sched._reset_embedder_cache(unload=False)


def test_b554_reset_embedder_cache_unloads_and_clears(monkeypatch):
    """_reset_embedder_cache(unload=True) ruft unload() auf der persistenten
    Instanz und leert den Cache (VRAM-Hygiene beim Scheduler-Stop)."""
    from types import SimpleNamespace

    import services.brain_v3.video.video_embedder as ve
    from services.brain_v3 import embedding_scheduler as sched

    unloaded = {"n": 0}

    class _UnloadEmbedder:
        def __init__(self, serializer=None):
            pass

        def embed_clip(self, source_path, video_hash):
            return SimpleNamespace(clip_embedding=np.zeros(8, dtype=np.float32))

        def unload(self):
            unloaded["n"] += 1

    sched._reset_embedder_cache(unload=False)
    monkeypatch.setattr(ve, "Siglip2VideoEmbedder", _UnloadEmbedder)
    monkeypatch.setattr(ve, "SIGLIP2_MODEL_ID", "fake/siglip2")
    monkeypatch.setattr(ve, "SIGLIP2_MODEL_VERSION", "0.0")
    task = EmbeddingTask(
        media_hash="a" * 64, media_type="video", source_path=Path("a.mp4"),
    )
    sched._default_embedder_factory(
        task, lambda p, m: None, GpuSerializer(empty_cache_on_release=False),
    )
    assert sched._VIDEO_EMBEDDER is not None
    sched._reset_embedder_cache(unload=True)
    assert unloaded["n"] == 1
    assert sched._VIDEO_EMBEDDER is None
