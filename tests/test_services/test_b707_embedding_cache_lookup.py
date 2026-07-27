"""B-707: Der Embedding-Cache war WRITE-ONLY — `EmbeddingCache.lookup` hatte
0 Callsites, `submit_path` rechnete jeden Import neu.

Beweispflicht dieser Tests: ein ZWEITER Durchlauf mit identischem Inhalt ruft
den Embedder NICHT erneut auf (GPU-Arbeit uebersprungen), eine INHALTS-
AENDERUNG loest ihn wieder aus. Ausserdem: Invalidierung bei Modell-Wechsel,
Dimensions-Wechsel und fehlender .npy-Datei.

Alle Embedder sind gemockt (Aufruf-Zaehler) — kein torch, keine GPU.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from PySide6.QtWidgets import QApplication

from services.brain.embedding_scheduler import (
    EmbeddingScheduler,
    EmbeddingTask,
    ModelIdentity,
    _cache_lookup,
    _default_model_identity,
    reset_default_scheduler_for_tests,
)
from services.brain.gpu_serializer import (
    GpuSerializer,
    reset_default_serializer_for_tests,
)
from services.brain.hashing import compute_media_hash
from services.brain.storage.embedding_cache import EmbeddingCache
from services.brain.storage.media_hash_registry import MediaHashRegistry

FAKE_MODEL = "fake/model"
FAKE_VERSION = "0.0"
FAKE_DIM = 8


@pytest.fixture(scope="module")
def qt_app():
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


def _fake_identity(media_type: str):
    """Resolver passend zur Zaehl-Factory unten."""
    return ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM)


class _CountingFactory:
    """Embedder-Ersatz, der jeden echten Rechen-Aufruf mitzaehlt."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, task, progress_cb, serializer):
        self.calls.append(task.media_hash)
        progress_cb(0.5, "fake-compute")
        return {
            "embedding": np.zeros(FAKE_DIM, dtype=np.float32),
            "model_name": FAKE_MODEL,
            "model_version": FAKE_VERSION,
        }


def _spin_qt(app, ms: int = 100) -> None:
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)


def _wait_for(app, predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        _spin_qt(app, 50)
    return predicate()


def _make_scheduler(cache: EmbeddingCache, factory) -> EmbeddingScheduler:
    return EmbeddingScheduler(
        n_workers=1,
        cache=cache,
        embedder_factory=factory,
        serializer=GpuSerializer(empty_cache_on_release=False),
        model_identity_resolver=_fake_identity,
    )


# ----------------------------------------------------------------------
# Kern-Beweis: zweiter Lauf ueberspringt die Berechnung
# ----------------------------------------------------------------------
def test_b707_second_run_same_content_skips_embedder(qt_app, isolated_appdata):
    """Zwei Importe DERSELBEN Datei -> Embedder wird genau EINMAL gerufen.

    Der Hash kommt aus dem echten Produktions-Pfad (MediaHashRegistry ->
    compute_media_hash), nicht aus einem Literal.
    """
    media = isolated_appdata / "clip.mp4"
    media.write_bytes(b"video-bytes-v1" * 500)

    registry = MediaHashRegistry()
    hash_1 = registry.register(media, "video").entry.media_hash

    cache = EmbeddingCache()
    factory = _CountingFactory()
    scheduler = _make_scheduler(cache, factory)
    skipped: list[tuple[str, str]] = []
    scheduler.job_skipped.connect(lambda h, r: skipped.append((h, r)))
    scheduler.start()
    try:
        # --- Lauf 1: Miss -> Job -> Embedder rechnet -> store() ---
        job_id = scheduler.submit_path(hash_1, media, "video")
        assert job_id is not None, "Lauf 1 haette ein Cache-Miss sein muessen"
        assert _wait_for(
            qt_app, lambda: cache.lookup(hash_1, FAKE_MODEL, FAKE_VERSION) is not None
        ), "Lauf 1 hat kein Embedding persistiert"
        assert factory.calls == [hash_1], f"Lauf 1 Aufrufe: {factory.calls}"

        # --- Lauf 2: identischer Inhalt -> gleicher Hash -> Cache-Hit ---
        hash_2 = registry.register(media, "video").entry.media_hash
        assert hash_2 == hash_1, "gleicher Inhalt muss gleichen Hash ergeben"

        job_id_2 = scheduler.submit_path(hash_2, media, "video")
        assert job_id_2 is None, (
            "Cache-Hit muss None liefern (kein Job eingereiht), war: "
            f"{job_id_2!r}"
        )
        _spin_qt(qt_app, 300)  # Zeit lassen, falls doch ein Job liefe
        assert factory.calls == [hash_1], (
            "BEWEIS FEHLGESCHLAGEN: Embedder wurde beim zweiten Durchlauf "
            f"erneut gerufen. Aufrufe: {factory.calls}"
        )
        assert skipped and skipped[-1][0] == hash_1
        assert "cache-hit" in skipped[-1][1]
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_b707_changed_content_recomputes(qt_app, isolated_appdata):
    """Inhalts-AENDERUNG derselben Datei -> neuer sha256 -> Embedder rechnet erneut."""
    media = isolated_appdata / "clip.mp4"
    media.write_bytes(b"video-bytes-v1" * 500)

    registry = MediaHashRegistry()
    hash_v1 = registry.register(media, "video").entry.media_hash

    cache = EmbeddingCache()
    factory = _CountingFactory()
    scheduler = _make_scheduler(cache, factory)
    scheduler.start()
    try:
        assert scheduler.submit_path(hash_v1, media, "video") is not None
        assert _wait_for(
            qt_app, lambda: cache.lookup(hash_v1, FAKE_MODEL, FAKE_VERSION) is not None
        )
        assert factory.calls == [hash_v1]

        # Cache-Hit bestaetigen, BEVOR der Inhalt geaendert wird
        assert scheduler.submit_path(hash_v1, media, "video") is None

        # --- Inhalt aendern ---
        media.write_bytes(b"video-bytes-v2-COMPLETELY-DIFFERENT" * 500)
        hash_v2 = registry.register(media, "video").entry.media_hash
        assert hash_v2 != hash_v1, (
            "geaenderter Inhalt muss anderen sha256 ergeben — sonst ist der "
            "Cache-Key kein Inhalts-Hash"
        )

        job_id = scheduler.submit_path(hash_v2, media, "video")
        assert job_id is not None, "geaenderter Inhalt darf KEIN Cache-Hit sein"
        assert _wait_for(
            qt_app, lambda: cache.lookup(hash_v2, FAKE_MODEL, FAKE_VERSION) is not None
        ), "geaenderter Inhalt wurde nicht neu eingebettet"
        assert factory.calls == [hash_v1, hash_v2], (
            f"Embedder-Aufrufe falsch: {factory.calls}"
        )
    finally:
        scheduler.request_stop(timeout_ms=3000)


def test_b707_inflight_duplicate_hits_second_gate(qt_app, isolated_appdata):
    """Zwei Submits desselben Hashes, bevor der erste fertig ist: der zweite
    Job faengt den Hit am Gate in _execute_embedding ab (nicht in submit_path)."""
    media = isolated_appdata / "clip.mp4"
    media.write_bytes(b"dup" * 500)
    media_hash = compute_media_hash(media)

    cache = EmbeddingCache()
    factory = _CountingFactory()
    scheduler = _make_scheduler(cache, factory)
    scheduler.start()
    try:
        # Beide Submits VOR jeder Verarbeitung -> submit_path sieht 2x Miss.
        id_a = scheduler.submit_path(media_hash, media, "video")
        id_b = scheduler.submit_path(media_hash, media, "video")
        assert id_a is not None and id_b is not None

        assert _wait_for(
            qt_app,
            lambda: cache.lookup(media_hash, FAKE_MODEL, FAKE_VERSION) is not None,
        )
        _spin_qt(qt_app, 400)
        assert factory.calls == [media_hash], (
            "In-flight-Duplikat wurde doppelt gerechnet — zweiter Gate greift "
            f"nicht. Aufrufe: {factory.calls}"
        )
    finally:
        scheduler.request_stop(timeout_ms=3000)


# ----------------------------------------------------------------------
# Invalidierung
# ----------------------------------------------------------------------
def test_b707_lookup_invalidates_on_model_mismatch(isolated_appdata):
    cache = EmbeddingCache()
    task = EmbeddingTask("c" * 64, "video", Path("x.mp4"))
    cache.store(
        media_hash=task.media_hash, media_type="video",
        embedding=np.zeros(FAKE_DIM, dtype=np.float32),
        model_name=FAKE_MODEL, model_version=FAKE_VERSION,
    )
    assert _cache_lookup(cache, task, ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM)) is not None
    # anderer Modell-Name
    assert _cache_lookup(cache, task, ModelIdentity("other/model", FAKE_VERSION, FAKE_DIM)) is None
    # andere Modell-Version (Upgrade)
    assert _cache_lookup(cache, task, ModelIdentity(FAKE_MODEL, "2.0", FAKE_DIM)) is None


def test_b707_lookup_invalidates_on_dimension_mismatch(isolated_appdata):
    cache = EmbeddingCache()
    task = EmbeddingTask("d" * 64, "video", Path("x.mp4"))
    cache.store(
        media_hash=task.media_hash, media_type="video",
        embedding=np.zeros(FAKE_DIM, dtype=np.float32),
        model_name=FAKE_MODEL, model_version=FAKE_VERSION,
    )
    assert _cache_lookup(
        cache, task, ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM + 1)
    ) is None, "Vektor mit falscher Dimension muss verworfen werden"


def test_b707_lookup_invalidates_on_missing_npy(isolated_appdata):
    cache = EmbeddingCache()
    task = EmbeddingTask("e" * 64, "video", Path("x.mp4"))
    entry = cache.store(
        media_hash=task.media_hash, media_type="video",
        embedding=np.zeros(FAKE_DIM, dtype=np.float32),
        model_name=FAKE_MODEL, model_version=FAKE_VERSION,
    )
    entry.embedding_path.unlink()
    assert _cache_lookup(
        cache, task, ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM)
    ) is None, "Index-Eintrag ohne .npy muss als Miss gelten"


def test_b707_lookup_never_raises_on_broken_cache(isolated_appdata):
    """Ein defekter Cache darf den Embedding-Pfad nie blockieren."""
    class _BrokenCache:
        def lookup(self, *a, **kw):
            raise RuntimeError("db kaputt")

    task = EmbeddingTask("f" * 64, "video", Path("x.mp4"))
    assert _cache_lookup(
        _BrokenCache(), task, ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM)
    ) is None
    assert _cache_lookup(None, task, ModelIdentity(FAKE_MODEL, FAKE_VERSION, FAKE_DIM)) is None


# ----------------------------------------------------------------------
# Default-Resolver muss die REAL gespeicherten Identitaeten treffen
# ----------------------------------------------------------------------
def test_b707_default_identity_matches_production_constants():
    """Die 554 Live-Eintraege liegen unter genau diesen Identitaeten —
    der Default-Resolver muss sie exakt treffen, sonst bleibt der Cache tot."""
    from services.brain.audio.audio_embedder import (
        CLAP_MODEL_ID, CLAP_MODEL_VERSION, CLAP_DIM,
    )
    from services.brain.video.video_embedder import (
        SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION, SIGLIP2_DIM,
    )

    audio = _default_model_identity("audio")
    assert audio == ModelIdentity(CLAP_MODEL_ID, CLAP_MODEL_VERSION, CLAP_DIM)
    assert audio == ModelIdentity("laion/larger_clap_music", "1.0", 512)

    video = _default_model_identity("video")
    assert video == ModelIdentity(SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION, SIGLIP2_DIM)
    assert video == ModelIdentity("google/siglip2-base-patch16-384", "1.0", 768)

    assert _default_model_identity("bogus") is None
