import logging

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def test_style_bucket_clusterer_small_library_returns_degraded_result():
    from services.enrichment.style_bucket_clusterer import StyleBucketClusterer

    clusterer = StyleBucketClusterer()
    embeddings = np.zeros((1, 1152), dtype=np.float32)

    result = clusterer.fit_predict(embeddings)

    assert len(result.labels) == 1
    assert result.labels[0] == 0
    assert getattr(result, "degraded", False) is True
    assert result.reason == "small_library:1"


def test_structure_enrichment_small_library_finishes_degraded(monkeypatch, caplog):
    from workers.structure_enrichment import StructureEnrichmentWorker

    caplog.set_level(logging.INFO)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE scenes ("
                "id INTEGER PRIMARY KEY, video_clip_id INTEGER, start_time REAL, "
                "end_time REAL, ai_caption TEXT, ai_mood TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE struct_clip_tags ("
                "scene_id INTEGER PRIMARY KEY, role TEXT, role_confidence REAL, "
                "mood_refined TEXT, mood_confidence REAL, style_bucket_id INTEGER, "
                "style_distance REAL, enriched_at TEXT, enricher_version TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE struct_style_bucket ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, "
                "centroid_embedding BLOB, member_count INTEGER, created_at TEXT, "
                "enricher_version TEXT, active INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE struct_compat_edge ("
                "scene_id_a INTEGER, scene_id_b INTEGER, cosine_similarity REAL, "
                "rank_in_a INTEGER, PRIMARY KEY (scene_id_a, scene_id_b))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scenes "
                "(id, video_clip_id, start_time, end_time, ai_caption, ai_mood) "
                "VALUES (1, 1, 0.0, 1.0, '{\"tags\": []}', 'neutral')"
            )
        )

    class _FakeMoodMatcher:
        def __init__(self, *args, **kwargs):
            pass

        def refine(self, *args, **kwargs):
            return "neutral", 1.0

    class _FakeVectorDB:
        def get_all_embeddings(self):
            return (
                np.zeros((1, 1152), dtype=np.float32),
                [{"id": 1_000_000, "scene_index": 0}],
            )

    class _FakeCompatGraphBuilder:
        def __init__(self, *args, **kwargs):
            pass

        def build(self, *args, **kwargs):
            return []

    def _session_factory():
        return Session(engine)

    worker = StructureEnrichmentWorker(clip_id=None, session_factory=_session_factory)
    result = worker._do_enrich(
        session=_session_factory(),
        classify_role=lambda **_kwargs: ("texture", 1.0),
        MoodAnchorMatcher=_FakeMoodMatcher,
        StyleBucketClusterer=__import__(
            "services.enrichment.style_bucket_clusterer",
            fromlist=["StyleBucketClusterer"],
        ).StyleBucketClusterer,
        CompatGraphBuilder=_FakeCompatGraphBuilder,
        VectorDBService=_FakeVectorDB,
    )

    assert "error" not in result
    assert result["degraded"] is True
    assert result["scenes_enriched"] == 1
    assert "Single-Bucket-Degraded-Modus" in caplog.text
