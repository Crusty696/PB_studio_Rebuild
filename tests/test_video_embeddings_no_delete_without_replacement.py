"""Regression: Video-Embeddings duerfen nicht ohne Ersatz geloescht werden.

Zwei zusammenhaengende Befunde aus dem Audit vom 2026-07-26:

1. ``store_embeddings`` loeschte ALLE Vektoren eines Clips, BEVOR feststand,
   ob ueberhaupt neue entstehen. ``generate_embeddings`` kehrt bei fehlenden
   Keyframes und bei einem SigLIP-Ladefehler ohne Exception zurueck — eine
   Re-Analyse loeschte damit still die vorhandenen Embeddings.
2. ``run_full_pipeline`` meldete ``siglip_embeddings`` und
   ``vector_db_storage`` per ``mark_done`` gruen, obwohl 0 Embeddings
   existierten. Der Clip galt als 100 % analysiert.

Die Tests laufen rein mit Stubs — kein GPU-Modell, kein LanceDB, kein
echter FFmpeg-Aufruf, keine Schreibzugriffe auf die reale Projekt-DB.
"""

from __future__ import annotations

import numpy as np
import pytest

import services.vector_db_service as vector_db_service
from services import analysis_status_service
from services import video_analysis_service as vas
from services.video_analysis_service import SceneInfo, store_embeddings


class _FakeVectorDB:
    """Protokolliert Aufrufe statt LanceDB/SQLite anzufassen."""

    calls: list[tuple] = []

    def __init__(self):
        _FakeVectorDB.calls.append(("init",))

    def count(self) -> int:
        return 7

    def delete_by_clip_ids(self, clip_ids):
        _FakeVectorDB.calls.append(("delete", list(clip_ids)))

    def add_embeddings_batch(self, clip_id, entries):
        _FakeVectorDB.calls.append(("add", clip_id, len(entries)))


@pytest.fixture
def fake_vdb(monkeypatch):
    _FakeVectorDB.calls = []
    monkeypatch.setattr(vector_db_service, "VectorDBService", _FakeVectorDB)
    return _FakeVectorDB


def _scene(index: int, with_embedding: bool) -> SceneInfo:
    scene = SceneInfo(index=index, start_time=index * 2.0, end_time=index * 2.0 + 2.0)
    if with_embedding:
        scene.embedding = np.zeros(1152, dtype=np.float32)
    return scene


# ---------------------------------------------------------------------------
# Befund 1 — Delete-vor-Insert ohne Guard
# ---------------------------------------------------------------------------

def test_store_embeddings_does_not_delete_when_no_embeddings(fake_vdb):
    """SigLIP lieferte nichts -> vorhandene Vektoren muessen erhalten bleiben."""
    scenes = [_scene(0, False), _scene(1, False)]

    stored = store_embeddings("/tmp/clip.mp4", scenes, video_clip_id=42)

    assert stored == 0
    assert not any(c[0] == "delete" for c in fake_vdb.calls), (
        f"delete_by_clip_ids wurde ohne Ersatz-Embeddings aufgerufen: {fake_vdb.calls}"
    )
    assert not any(c[0] == "add" for c in fake_vdb.calls)


def test_store_embeddings_deletes_then_writes_when_embeddings_exist(fake_vdb):
    """Regulaerer Pfad bleibt unveraendert: erst loeschen, dann schreiben."""
    scenes = [_scene(0, True), _scene(1, True), _scene(2, False)]

    stored = store_embeddings("/tmp/clip.mp4", scenes, video_clip_id=42)

    assert stored == 2
    kinds = [c[0] for c in fake_vdb.calls if c[0] in ("delete", "add")]
    assert kinds == ["delete", "add"], fake_vdb.calls
    assert ("delete", [42]) in fake_vdb.calls
    assert ("add", 42, 2) in fake_vdb.calls


# ---------------------------------------------------------------------------
# Befund 2 — mark_done trotz 0 Embeddings
# ---------------------------------------------------------------------------

@pytest.fixture
def status_recorder(monkeypatch):
    """Faengt alle analysis_status_service-Aufrufe ab (keine DB-Writes)."""
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        analysis_status_service, "mark_started",
        lambda mt, mid, step: recorded.append((step, "started")),
    )
    monkeypatch.setattr(
        analysis_status_service, "mark_done",
        lambda mt, mid, step, summary=None: recorded.append((step, "done")),
    )
    monkeypatch.setattr(
        analysis_status_service, "mark_error",
        lambda mt, mid, step, msg: recorded.append((step, "error")),
    )
    monkeypatch.setattr(
        analysis_status_service, "mark_degraded",
        lambda mt, mid, step, reason, summary=None: recorded.append((step, "degraded")),
    )
    return recorded


def _stub_pipeline(monkeypatch, *, embeddings_present: bool, stored_count: int):
    """Ersetzt alle schweren Pipeline-Schritte durch Stubs."""
    scenes = [_scene(0, embeddings_present), _scene(1, embeddings_present)]

    monkeypatch.setattr(vas, "detect_scenes", lambda path, threshold=27.0: scenes)
    monkeypatch.setattr(
        vas, "compute_motion_scores",
        lambda path, sc, raft_model_device=None: sc,
    )
    monkeypatch.setattr(
        vas, "extract_keyframes",
        lambda path, sc, output_dir=None, progress_cb=None: sc,
    )
    monkeypatch.setattr(
        vas, "generate_embeddings",
        lambda sc, progress_cb=None, siglip_model_processor=None: sc,
    )
    monkeypatch.setattr(vas, "analyze_scene_with_caption", lambda sc, **kw: sc)
    monkeypatch.setattr(
        vas, "store_scenes_in_db",
        lambda clip_id, sc, expected_db_url=None: True,
    )
    monkeypatch.setattr(
        vas, "store_embeddings",
        lambda path, sc, clip_id: stored_count,
    )
    monkeypatch.setattr(vas, "_run_structure_enrichment", lambda clip_id: None)
    return scenes


def test_pipeline_marks_degraded_when_no_embeddings(
    monkeypatch, tmp_path, test_engine, video_clip, status_recorder,
):
    """0 Embeddings darf NICHT als 'done' gemeldet werden."""
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"not-a-real-video")
    _stub_pipeline(monkeypatch, embeddings_present=False, stored_count=0)

    vas.run_full_pipeline(str(video_file), video_clip.id)

    assert ("siglip_embeddings", "degraded") in status_recorder, status_recorder
    assert ("siglip_embeddings", "done") not in status_recorder, status_recorder
    assert ("vector_db_storage", "degraded") in status_recorder, status_recorder
    assert ("vector_db_storage", "done") not in status_recorder, status_recorder


def test_pipeline_marks_done_when_embeddings_exist(
    monkeypatch, tmp_path, test_engine, video_clip, status_recorder,
):
    """Gegenprobe: der Gutfall bleibt 'done' (kein Ueber-Melden von degraded)."""
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"not-a-real-video")
    _stub_pipeline(monkeypatch, embeddings_present=True, stored_count=2)

    vas.run_full_pipeline(str(video_file), video_clip.id)

    assert ("siglip_embeddings", "done") in status_recorder, status_recorder
    assert ("vector_db_storage", "done") in status_recorder, status_recorder
    assert ("siglip_embeddings", "degraded") not in status_recorder
    assert ("vector_db_storage", "degraded") not in status_recorder
