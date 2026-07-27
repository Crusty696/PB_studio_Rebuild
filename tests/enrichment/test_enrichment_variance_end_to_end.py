"""tests/enrichment/test_enrichment_variance_end_to_end.py

Worker-Ebene: ``StructureEnrichmentWorker`` muss nach einem Lauf in
``struct_clip_tags`` Werte hinterlassen, die ueber die Szenen VARIIEREN.

Warum genau so getestet: der urspruengliche Bug bestand darin, dass alle
Zeilen *gesetzt* waren (``role='filler'``, ``role_confidence=0.3``) — nur eben
alle gleich. Ein Existenztest war gruen, die Bewertungsachsen trotzdem tot.
Deshalb pruefen die Assertions hier "distinct > 1" und "max-min > 0".

Harness bewusst schlank gehalten (Muster von
``tests/enrichment/test_small_library_degraded.py``): In-Memory-SQLite,
Fakes fuer MoodMatcher / CompatGraphBuilder / VectorDB. Es wird KEIN
Modell geladen und keine GPU angefasst.

Run:
    python -m pytest tests/enrichment/test_enrichment_variance_end_to_end.py -p no:randomly -q
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.enrichment.role_embedding_classifier import (
    DEFAULT_PROTOTYPES_PATH,
    RoleEmbeddingClassifier,
)

_needs_prototypes = pytest.mark.skipif(
    not DEFAULT_PROTOTYPES_PATH.exists(),
    reason="config/role_prototypes.npz fehlt (scripts/generate_role_prototypes.py)",
)

_N_SCENES = 6

# Deutlich unterschiedliche Volltoene -> garantiert unterschiedliche
# brightness / saturation / color_temp.
_PALETTE = [
    (12, 12, 40),
    (210, 70, 25),
    (25, 95, 215),
    (245, 240, 225),
    (85, 165, 65),
    (155, 25, 165),
]


def _make_schema(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE scenes ("
            "id INTEGER PRIMARY KEY, video_clip_id INTEGER, start_time REAL, "
            "end_time REAL, ai_caption TEXT, ai_mood TEXT, "
            "scene_index INTEGER, keyframe_paths TEXT)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE video_clips ("
            "id INTEGER PRIMARY KEY, project_id INTEGER, file_path TEXT, "
            "proxy_path TEXT)"
        )
    )
    # Schema inkl. der von Revision f2a3b4c5d6e7 nachgeruesteten Spalten.
    conn.execute(
        text(
            "CREATE TABLE struct_clip_tags ("
            "scene_id INTEGER PRIMARY KEY, role TEXT, role_confidence REAL, "
            "mood_refined TEXT, mood_confidence REAL, style_bucket_id INTEGER, "
            "style_distance REAL, enriched_at TEXT, enricher_version TEXT, "
            "avg_brightness REAL, avg_saturation REAL, color_temp REAL, "
            "visual_frame_count INTEGER, visual_metrics_version TEXT, "
            "role_source TEXT)"
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


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Migrierte Mini-DB + echte Keyframe-JPEGs + prototypnahe Embeddings."""
    import workers.structure_enrichment as se

    kf_dir = tmp_path / "storage" / "keyframes"
    kf_dir.mkdir(parents=True)
    for i, rgb in enumerate(_PALETTE[:_N_SCENES]):
        arr = np.zeros((48, 64, 3), dtype=np.uint8)
        arr[:, :] = np.array(rgb, dtype=np.uint8)
        Image.fromarray(arr).save(kf_dir / f"clip1_proxy_scene{i:04d}.jpg", quality=95)

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _make_schema(conn)
        conn.execute(
            text(
                "INSERT INTO video_clips (id, project_id, file_path, proxy_path) "
                "VALUES (1, 1, '/fake/clip1.mp4', '/fake/proxies/clip1_proxy.mp4')"
            )
        )
        for i in range(_N_SCENES):
            conn.execute(
                text(
                    "INSERT INTO scenes (id, video_clip_id, start_time, end_time, "
                    "ai_caption, ai_mood, scene_index, keyframe_paths) "
                    "VALUES (:id, 1, :s, :e, '{\"tags\": [\"jungle\", \"dancer\"]}', "
                    "'ambient', NULL, NULL)"
                ),
                {"id": i + 1, "s": i * 5.0, "e": i * 5.0 + 5.0},
            )

    # Embeddings: pro Szene ein anderer Rollen-Prototyp + leichtes Rauschen.
    clf = RoleEmbeddingClassifier()
    rng = np.random.default_rng(3)
    roles = clf.roles[:_N_SCENES]
    embs = np.stack(
        [
            clf._get_prototype(r)
            + rng.standard_normal(clf.dim).astype(np.float32) * 0.02
            for r in roles
        ],
        axis=0,
    )

    monkeypatch.setattr(se, "_keyframe_dir", lambda: kf_dir)
    monkeypatch.setattr(se, "_REDUCER_PATH", tmp_path / "umap_v1.pkl")

    class _FakeMoodMatcher:
        def __init__(self, *a, **k):
            pass

        def refine(self, *a, **k):
            return "ambient", 0.5

    class _FakeCompat:
        def __init__(self, *a, **k):
            pass

        def build(self, *a, **k):
            return []

    class _FakeVectorDB:
        def get_all_embeddings(self):
            return embs, [
                {"id": 1_000_000 + i, "scene_index": i, "motion_score": 0.2 + 0.1 * i}
                for i in range(_N_SCENES)
            ]

    from services.enrichment.role_classifier import classify_role_detail
    from services.enrichment.style_bucket_clusterer import StyleBucketClusterer

    def run() -> dict:
        worker = se.StructureEnrichmentWorker(
            clip_id=None, session_factory=lambda: Session(engine)
        )
        return worker._do_enrich(
            session=Session(engine),
            classify_role_detail=classify_role_detail,
            MoodAnchorMatcher=_FakeMoodMatcher,
            StyleBucketClusterer=StyleBucketClusterer,
            CompatGraphBuilder=_FakeCompat,
            VectorDBService=_FakeVectorDB,
        )

    return {"engine": engine, "run": run, "expected_roles": roles}


@_needs_prototypes
def test_worker_writes_varying_visual_metrics(env):
    result = env["run"]()
    assert "error" not in result
    assert result["scenes_enriched"] == _N_SCENES
    assert result["visual_metrics_written"] == _N_SCENES

    with env["engine"].begin() as conn:
        rows = conn.execute(
            text(
                "SELECT avg_brightness, avg_saturation, color_temp, "
                "visual_frame_count, visual_metrics_version "
                "FROM struct_clip_tags ORDER BY scene_id"
            )
        ).fetchall()

    assert len(rows) == _N_SCENES
    for col_idx, label in ((0, "avg_brightness"), (1, "avg_saturation"), (2, "color_temp")):
        vals = [r[col_idx] for r in rows]
        assert all(v is not None for v in vals), f"{label} enthaelt NULL"
        assert max(vals) - min(vals) > 0.0, f"{label} ist ueber alle Clips konstant"
        assert len({round(v, 6) for v in vals}) == _N_SCENES, (
            f"{label} hat nur {len({round(v, 6) for v in vals})} distinkte Werte"
        )
    assert all(r[3] == 1 for r in rows)
    assert all(r[4] == "vm1" for r in rows)


@_needs_prototypes
def test_worker_writes_varying_roles_from_embeddings(env):
    result = env["run"]()
    assert result["role_sources"]["embedding"] == _N_SCENES
    assert result["role_sources"]["unknown"] == 0
    assert result["distinct_roles"] > 1

    with env["engine"].begin() as conn:
        rows = conn.execute(
            text(
                "SELECT role, role_confidence, role_source "
                "FROM struct_clip_tags ORDER BY scene_id"
            )
        ).fetchall()

    roles = [r[0] for r in rows]
    confs = [r[1] for r in rows]
    assert set(roles) == set(env["expected_roles"]), (
        f"erwartet {sorted(set(env['expected_roles']))}, bekommen {sorted(set(roles))}"
    )
    assert "filler" not in roles or len(set(roles)) > 1
    assert max(confs) - min(confs) > 0.0, "role_confidence ist konstant"
    assert len({round(c, 6) for c in confs}) > 1
    assert all(r[2] == "embedding" for r in rows)


@_needs_prototypes
def test_missing_prototypes_yield_unknown_not_silent_filler(env, monkeypatch, tmp_path):
    """Ohne Prototypen: ehrlich ``unknown`` + Grund, kein stiller ``filler``."""
    import workers.structure_enrichment as se

    monkeypatch.setattr(se, "_ROLE_PROTOTYPES_PATH", tmp_path / "absent.npz")
    result = env["run"]()

    assert "error" not in result
    assert result["role_sources"]["unknown"] == _N_SCENES
    with env["engine"].begin() as conn:
        rows = conn.execute(
            text("SELECT role, role_source FROM struct_clip_tags")
        ).fetchall()
    assert {r[0] for r in rows} == {"unknown"}
    assert all(r[1].startswith("unknown:no_prototypes") for r in rows)


@_needs_prototypes
def test_missing_keyframes_leave_null_not_a_default(env, monkeypatch, tmp_path):
    """Kein auffindbarer Keyframe -> NULL, nicht 0.5."""
    import workers.structure_enrichment as se

    empty = tmp_path / "no_keyframes"
    empty.mkdir()
    monkeypatch.setattr(se, "_keyframe_dir", lambda: empty)
    result = env["run"]()

    assert "error" not in result
    assert result["visual_metrics_written"] == 0
    with env["engine"].begin() as conn:
        rows = conn.execute(
            text("SELECT avg_brightness, color_temp FROM struct_clip_tags")
        ).fetchall()
    assert all(r[0] is None and r[1] is None for r in rows)
