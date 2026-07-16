"""B-640: Stub-VLM-Captions duerfen NICHT als echte Scene.ai_caption in DB
landen.

Root-Cause: Die Live-Video-Pipeline instanziiert ``VlmCaptionStage()`` ohne
``llm_backend`` -> laeuft dauerhaft im Stub-Mode, jede Szene bekam bisher
den Platzhaltertext "[VLM not wired — Plan B Phase 11 pending]" als echte
DB-Caption persistiert (verunreinigt Scene-Tabelle + VectorDB).

User-Entscheidung (Autonomie-Freigabe): Option B — Stub-Captions NICHT
persistieren (None statt Platzhalter), bis das echte VLM-Backend (Plan B
Phase 11) steht. Fix in ``db_persist_stage.py``: Caption-Zeilen mit
``model_id == "stub-vlm"`` (der von ``VlmCaptionService.stub_model_id``
gesetzte Marker, landet unveraendert in ``captions.json``) werden beim
Scene-DB-Mapping uebersprungen.
"""
import json

import numpy as np

from services.video_pipeline.stages.db_persist_stage import DbPersistStage
from services.video_pipeline.stages.vlm_caption_service import VlmCaptionService


def _write_artifacts(storage_dir, *, scenes, keyframes, embeddings,
                     motion, captions=None):
    (storage_dir / "scenes.json").write_text(json.dumps(scenes))
    (storage_dir / "keyframes.json").write_text(json.dumps(keyframes))
    (storage_dir / "motion.json").write_text(json.dumps(motion))
    if captions is not None:
        (storage_dir / "captions.json").write_text(json.dumps(captions))
    if embeddings is not None:
        np.save(storage_dir / "embeddings.npy", embeddings)


def _patch_writers(monkeypatch):
    import services.video_analysis_service as vas
    captured = {"scenes": None, "embeds": None}

    def fake_store_scenes(clip_id, scene_infos, expected_db_url=None):
        captured["scenes"] = (clip_id, scene_infos, expected_db_url)
        return True

    def fake_store_embeddings(video_path, scene_infos, clip_id):
        captured["embeds"] = (video_path, scene_infos, clip_id)
        return sum(1 for s in scene_infos if s.embedding is not None)

    monkeypatch.setattr(vas, "store_scenes_in_db", fake_store_scenes)
    monkeypatch.setattr(vas, "store_embeddings", fake_store_embeddings)
    return captured


def test_stub_model_id_matches_real_default():
    """Der Marker-String im Fix muss exakt dem echten Default aus
    VlmCaptionService entsprechen — sonst greift der Filter still nicht,
    wenn sich der Default je aendert."""
    svc = VlmCaptionService()
    assert svc.stub_model_id == "stub-vlm"


def test_stub_caption_not_persisted_as_ai_caption(tmp_path, monkeypatch):
    """Kernfall: captions.json enthaelt eine Stub-Caption (model_id=stub-vlm)
    -> ai_caption bleibt None statt des Platzhaltertexts."""
    captured = _patch_writers(monkeypatch)
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0}],
        keyframes=[{"scene_idx": 0, "role": "mid", "time_s": 1.0, "path": "k0.jpg"}],
        embeddings=np.arange(1 * 4, dtype=np.float32).reshape(1, 4),
        motion=[{"pair_index": 0, "time_a_s": 0.5, "time_b_s": 1.5, "mean_magnitude": 30.0}],
        captions=[{
            "scene_idx": 0,
            "text": "[VLM not wired — Plan B Phase 11 pending]",
            "model_id": "stub-vlm",
        }],
    )
    stage = DbPersistStage(clip_id=1, expected_db_url="sqlite:///proj.db")
    res = stage.run(tmp_path / "video.mp4", tmp_path)

    assert res.status == "done"
    _clip_id, scene_infos, _expected = captured["scenes"]
    assert scene_infos[0].ai_caption is None, (
        "B-640: Stub-Caption wurde trotz model_id=stub-vlm persistiert"
    )


def test_real_caption_with_other_model_id_still_persisted(tmp_path, monkeypatch):
    """Gegenprobe: eine ECHTE Caption (anderer model_id) muss weiterhin
    persistiert werden — der Fix darf keine echten Captions unterdruecken."""
    captured = _patch_writers(monkeypatch)
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0}],
        keyframes=[{"scene_idx": 0, "role": "mid", "time_s": 1.0, "path": "k0.jpg"}],
        embeddings=np.arange(1 * 4, dtype=np.float32).reshape(1, 4),
        motion=[{"pair_index": 0, "time_a_s": 0.5, "time_b_s": 1.5, "mean_magnitude": 30.0}],
        captions=[{
            "scene_idx": 0,
            "text": "a person dancing on stage",
            "model_id": "real-vlm-v1",
        }],
    )
    stage = DbPersistStage(clip_id=1, expected_db_url="sqlite:///proj.db")
    res = stage.run(tmp_path / "video.mp4", tmp_path)

    assert res.status == "done"
    _clip_id, scene_infos, _expected = captured["scenes"]
    assert scene_infos[0].ai_caption == {"description": "a person dancing on stage"}


def test_caption_without_model_id_field_still_persisted(tmp_path, monkeypatch):
    """Rueckwaertskompat: captions.json ohne model_id-Feld (aeltere Artefakte
    oder Test-Fixtures) duerfen nicht faelschlich als Stub gefiltert werden."""
    captured = _patch_writers(monkeypatch)
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0}],
        keyframes=[{"scene_idx": 0, "role": "mid", "time_s": 1.0, "path": "k0.jpg"}],
        embeddings=np.arange(1 * 4, dtype=np.float32).reshape(1, 4),
        motion=[{"pair_index": 0, "time_a_s": 0.5, "time_b_s": 1.5, "mean_magnitude": 30.0}],
        captions=[{"scene_idx": 0, "text": "a quiet room"}],
    )
    stage = DbPersistStage(clip_id=1, expected_db_url="sqlite:///proj.db")
    res = stage.run(tmp_path / "video.mp4", tmp_path)

    assert res.status == "done"
    _clip_id, scene_infos, _expected = captured["scenes"]
    assert scene_infos[0].ai_caption == {"description": "a quiet room"}
