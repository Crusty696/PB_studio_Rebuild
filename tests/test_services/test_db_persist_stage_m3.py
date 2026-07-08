"""NEUBAU-VOLLINTEGRATION M3 (D-065 / PIPE-018): DbPersistStage.

Die DAG-Engine schrieb bisher nur Datei-Artefakte, nicht in Scene/VectorDB.
DbPersistStage liest die Artefakte und fuettert die bewaehrten
Monolith-Writer (store_scenes_in_db, store_embeddings). Diese Tests pruefen
die Adapter-Logik (Artefakt -> SceneInfo) ohne echte DB/LanceDB — die
Writer werden gemockt.
"""
import json

import numpy as np

from services.video_pipeline.stages.db_persist_stage import DbPersistStage


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


def test_maps_artifacts_to_scene_infos(tmp_path, monkeypatch):
    captured = _patch_writers(monkeypatch)
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0},
                {"index": 1, "start_s": 2.0, "end_s": 4.0}],
        keyframes=[{"scene_idx": 0, "role": "mid", "time_s": 1.0, "path": "k0.jpg"},
                   {"scene_idx": 1, "role": "mid", "time_s": 3.0, "path": "k1.jpg"}],
        embeddings=np.arange(2 * 4, dtype=np.float32).reshape(2, 4),
        motion=[{"pair_index": 0, "time_a_s": 0.5, "time_b_s": 1.5, "mean_magnitude": 30.0},
                {"pair_index": 1, "time_a_s": 2.5, "time_b_s": 3.5, "mean_magnitude": 80.0}],
        captions=[{"scene_idx": 0, "text": "a quiet room"},
                  {"scene_idx": 1, "text": "fast action"}],
    )
    stage = DbPersistStage(clip_id=77, expected_db_url="sqlite:///proj.db")
    res = stage.run(tmp_path / "video.mp4", tmp_path)

    assert res.status == "done"
    assert res.metrics["scenes_written"] == 2
    assert res.metrics["embeddings_written"] == 2

    clip_id, scene_infos, expected = captured["scenes"]
    assert clip_id == 77
    assert expected == "sqlite:///proj.db"
    assert len(scene_infos) == 2
    # Motion normalisiert (1-exp(-raw/40)): Szene 1 (80px) > Szene 0 (30px)
    assert scene_infos[1].motion_score > scene_infos[0].motion_score > 0.0
    # Embedding je Szene aus der passenden Keyframe-Zeile
    assert np.allclose(scene_infos[0].embedding, [0, 1, 2, 3])
    assert np.allclose(scene_infos[1].embedding, [4, 5, 6, 7])
    # Caption als description; mood/tags bleiben None (Stub-VLM ehrlich)
    assert scene_infos[0].ai_caption == {"description": "a quiet room"}
    assert scene_infos[0].ai_mood is None
    assert scene_infos[0].ai_tags is None


def test_missing_scenes_is_failed(tmp_path, monkeypatch):
    _patch_writers(monkeypatch)
    stage = DbPersistStage(clip_id=1)
    res = stage.run(tmp_path / "v.mp4", tmp_path)
    assert res.status == "failed"
    assert "scenes.json" in res.error


def test_scene_skip_blocks_embeddings(tmp_path, monkeypatch):
    """Wenn store_scenes_in_db skip meldet (Projekt-Mismatch), duerfen keine
    Embeddings geschrieben werden (sonst verwaiste VectorDB-Rows)."""
    import services.video_analysis_service as vas
    calls = {"embeds": 0}
    monkeypatch.setattr(vas, "store_scenes_in_db",
                        lambda *a, **k: False)
    monkeypatch.setattr(vas, "store_embeddings",
                        lambda *a, **k: calls.__setitem__("embeds", calls["embeds"] + 1))
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0}],
        keyframes=[{"scene_idx": 0, "role": "mid", "time_s": 1.0, "path": "k0.jpg"}],
        embeddings=np.zeros((1, 4), dtype=np.float32),
        motion=[],
    )
    res = DbPersistStage(clip_id=5).run(tmp_path / "v.mp4", tmp_path)
    assert res.status == "failed"
    assert calls["embeds"] == 0


def test_no_embeddings_still_writes_scenes(tmp_path, monkeypatch):
    captured = _patch_writers(monkeypatch)
    _write_artifacts(
        tmp_path,
        scenes=[{"index": 0, "start_s": 0.0, "end_s": 2.0}],
        keyframes=[],
        embeddings=None,
        motion=[{"pair_index": 0, "time_a_s": 0.5, "time_b_s": 1.5, "mean_magnitude": 20.0}],
    )
    res = DbPersistStage(clip_id=9).run(tmp_path / "v.mp4", tmp_path)
    assert res.status == "done"
    _, scene_infos, _ = captured["scenes"]
    assert scene_infos[0].embedding is None
    assert res.metrics["embeddings_written"] == 0


def test_build_pipeline_appends_db_persist_last():
    """Quelltext-Vertrag: build_pipeline haengt DbPersistStage als letzte
    Stage ein."""
    import inspect

    import services.video_pipeline.app_integration as ai
    src = inspect.getsource(ai.build_pipeline)
    assert "DbPersistStage(clip_id=track_id" in src
    # als letzte Stage vor dem Pipeline-Konstruktor
    assert src.index("DbPersistStage(") > src.index("CrossModalStage(")
