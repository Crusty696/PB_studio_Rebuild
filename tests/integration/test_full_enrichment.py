"""Integration test: StructureEnrichmentWorker — T4.1.

Uses a synthetic in-memory SQLite DB (at tmp_path) with Alembic migrations
run to head.  24 scenes across 3 clips in 3 tight Gaussian clusters so
HDBSCAN (min_cluster_size=8, 3 × 8 = 24) produces at least 2 non-noise
clusters with high probability.

Run with:
    pytest tests/integration/test_full_enrichment.py -v
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers (shared with test_alembic_migrations.py pattern)
# ---------------------------------------------------------------------------


def _make_alembic_cfg(db_path: Path) -> Config:
    ini_path = Path(__file__).parent.parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _make_engine(db_path: Path):
    eng = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(eng, "connect")
    def _set_pragmas(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return eng


def _make_session_factory(db_path: Path):
    """Return a callable that creates a plain SQLAlchemy Session for tmp DB."""
    eng = _make_engine(db_path)

    def factory() -> Session:
        return Session(eng)

    return factory


# ---------------------------------------------------------------------------
# Synthetic embedding generation (3 tight clusters in 1152-d)
# ---------------------------------------------------------------------------
_RNG = np.random.default_rng(42)
# 3 × 18 = 54 scenes total.
# - 54 > REFIT_THRESHOLD=50 → incremental runs use assign mode.
# - 18 >= HDBSCAN min_cluster_size=8 → clean clustering.
_N_PER_CLUSTER = 18
_N_CLUSTERS = 3
_DIM = 1152


def _make_cluster_embeddings() -> np.ndarray:
    """Generate N_CLUSTERS × N_PER_CLUSTER tight Gaussian clusters in 1152-d."""
    centres = _RNG.standard_normal((_N_CLUSTERS, _DIM)).astype(np.float32)
    # Normalise centres so cosine distances between clusters are large
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    # Scale centres apart (×10) so clusters don't overlap
    centres *= 10.0

    all_embs = []
    for c in centres:
        noise = _RNG.standard_normal((_N_PER_CLUSTER, _DIM)).astype(np.float32) * 0.05
        all_embs.append(c + noise)
    return np.vstack(all_embs)  # (24, 1152)


# ---------------------------------------------------------------------------
# DB seeding
# ---------------------------------------------------------------------------


def _seed_db(db_path: Path, embeddings: np.ndarray) -> None:
    """Insert 3 VideoClips × 8 Scenes each + a Project into the migrated DB.

    Clip 1 → scenes 1-8, Clip 2 → scenes 9-16, Clip 3 → scenes 17-24.
    scene_index (0-based) aligns with VectorDB composite_id computation.
    """
    total = embeddings.shape[0]
    assert total == _N_CLUSTERS * _N_PER_CLUSTER

    with sqlite3.connect(str(db_path)) as conn:
        # Project
        conn.execute(
            "INSERT INTO projects (id, name, path, resolution, fps) "
            "VALUES (1, 'test_project', '/fake', '1920x1080', 30.0)"
        )
        # 3 VideoClips
        for clip_id in range(1, _N_CLUSTERS + 1):
            conn.execute(
                "INSERT INTO video_clips (id, project_id, file_path, playback_offset) "
                f"VALUES ({clip_id}, 1, '/fake/clip{clip_id}.mp4', 0.0)"
            )
        # 8 Scenes per clip
        scene_id = 1
        for clip_id in range(1, _N_CLUSTERS + 1):
            for local_idx in range(_N_PER_CLUSTER):
                start = local_idx * 5.0
                end = start + 5.0
                ai_caption = json.dumps(
                    {"tags": ["outdoor", "motion"], "mood": "energetic"}
                )
                ai_mood = "energetic"
                conn.execute(
                    "INSERT INTO scenes (id, video_clip_id, start_time, end_time, "
                    "                   ai_caption, ai_mood) "
                    f"VALUES ({scene_id}, {clip_id}, {start}, {end}, ?, ?)",
                    (ai_caption, ai_mood),
                )
                scene_id += 1
        conn.commit()


def _inject_embeddings_into_vdb(vdb_db_path: Path, embeddings: np.ndarray) -> None:
    """Write embeddings directly into the VectorDB SQLite file.

    Uses clip_id * 1_000_000 + scene_index as composite id (mirrors VDB logic).
    """
    vdb_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(vdb_db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS clip_embeddings ("
            "    id INTEGER PRIMARY KEY,"
            "    video_path TEXT NOT NULL,"
            "    scene_index INTEGER NOT NULL,"
            "    scene_start REAL NOT NULL,"
            "    scene_end REAL NOT NULL,"
            "    motion_score REAL DEFAULT 0.0,"
            "    description TEXT DEFAULT '',"
            "    embedding BLOB NOT NULL"
            ")"
        )
        rows = []
        emb_idx = 0
        for clip_id in range(1, _N_CLUSTERS + 1):
            for local_idx in range(_N_PER_CLUSTER):
                composite_id = clip_id * 1_000_000 + local_idx
                emb_blob = embeddings[emb_idx].astype(np.float32).tobytes()
                rows.append(
                    (
                        composite_id,
                        f"/fake/clip{clip_id}.mp4",
                        local_idx,
                        local_idx * 5.0,
                        local_idx * 5.0 + 5.0,
                        0.5,
                        "",
                        emb_blob,
                    )
                )
                emb_idx += 1
        conn.executemany(
            "INSERT OR REPLACE INTO clip_embeddings "
            "(id, video_path, scene_index, scene_start, scene_end, "
            " motion_score, description, embedding) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def enrichment_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a fully migrated SQLite DB + seeded VectorDB for enrichment tests.

    Yields a dict with:
        db_path     — path to the main SQLite DB
        session_factory — callable returning a Session for that DB
        vdb_path    — path to the VectorDB SQLite
        embeddings  — the (24, 1152) numpy array used for seeding
        storage_dir — storage/enricher dir inside tmp_path (for reducer pickle)
    """
    from database.models import Base

    db_path = tmp_path / "pb_studio_test.db"
    cfg = _make_alembic_cfg(db_path)

    # 1. Create baseline tables via ORM metadata (mirrors production app startup).
    #    The initial Alembic migration is empty; real schema comes from create_all().
    studio_brain_tables = {
        "struct_clip_tags",
        "struct_style_bucket",
        "struct_compat_edge",
        "mem_pacing_run",
        "mem_decision",
        "mem_learned_pattern",
        "mem_user_feedback_event",
    }
    eng = _make_engine(db_path)
    try:
        tables_to_create = [
            t for t in Base.metadata.sorted_tables if t.name not in studio_brain_tables
        ]
        Base.metadata.create_all(eng, tables=tables_to_create)
    finally:
        eng.dispose()

    # 2. Stamp at last pre-Studio-Brain revision, then upgrade to head
    #    to create struct_* and mem_* tables via Alembic migrations.
    alembic_command.stamp(cfg, "a3df65cc10b1")
    alembic_command.upgrade(cfg, "head")

    # Generate synthetic embeddings
    embeddings = _make_cluster_embeddings()

    # Seed scenes into main DB
    _seed_db(db_path, embeddings)

    # Point VectorDBService at a fresh file inside tmp_path
    vdb_dir = tmp_path / "data" / "vector"
    vdb_db_path = vdb_dir / "embeddings.db"
    _inject_embeddings_into_vdb(vdb_db_path, embeddings)

    # Patch VectorDBService singleton to use our test file
    import services.vector_db_service as _vdb_mod

    original_instance = _vdb_mod._instance
    monkeypatch.setattr(_vdb_mod, "_instance", None)
    _vdb_mod.VectorDBService(db_path=vdb_db_path)

    # Storage dir for reducer pickle
    storage_dir = tmp_path / "storage" / "enricher"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Patch _REDUCER_PATH in the worker module
    import workers.structure_enrichment as _worker_mod

    monkeypatch.setattr(_worker_mod, "_REDUCER_PATH", storage_dir / "umap_v1.pkl")

    session_factory = _make_session_factory(db_path)

    yield {
        "db_path": db_path,
        "session_factory": session_factory,
        "vdb_db_path": vdb_db_path,
        "embeddings": embeddings,
        "storage_dir": storage_dir,
    }

    # Restore VDB singleton so other tests aren't affected
    monkeypatch.setattr(_vdb_mod, "_instance", original_instance)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_enrichment_fixture_vector_db_visible_to_worker(enrichment_env: dict) -> None:
    """Regression guard: worker's no-arg VectorDBService sees fixture DB."""
    from services.vector_db_service import VectorDBService

    expected_path = Path(enrichment_env["vdb_db_path"]).resolve()

    vdb = VectorDBService()
    assert Path(vdb.db_path).resolve() == expected_path

    matrix, metadata = vdb.get_all_embeddings()
    assert matrix.shape[0] == _N_CLUSTERS * _N_PER_CLUSTER
    assert len(metadata) == _N_CLUSTERS * _N_PER_CLUSTER


def test_full_enrichment_on_tiny_synthetic_library(
    enrichment_env: dict,
) -> None:
    """End-to-end: 24 synthetic scenes across 3 clips in 3 clusters.

    Asserts:
    - struct_clip_tags has 24 rows with role/mood/style populated.
    - struct_style_bucket has >= 2 active buckets.
    - struct_compat_edge has > 0 rows with rank_in_a in valid range.
    - ENRICHER_VERSION == "v1" on all tag rows.
    - Full-library mode → no AnalysisStatus row flipped (clip_id=None).
    """
    from workers.structure_enrichment import StructureEnrichmentWorker, ENRICHER_VERSION

    db_path: Path = enrichment_env["db_path"]
    session_factory = enrichment_env["session_factory"]

    worker = StructureEnrichmentWorker(
        clip_id=None,
        session_factory=session_factory,
        force_refit=False,
    )

    # Track emitted signals
    progress_calls: list[tuple[int, str]] = []
    finished_calls: list[dict] = []
    error_calls: list[str] = []

    worker.progress.connect(lambda pct, msg: progress_calls.append((pct, msg)))
    worker.finished.connect(lambda d: finished_calls.append(d))
    worker.error.connect(lambda e: error_calls.append(e))

    result = worker.run()

    total_scenes = _N_CLUSTERS * _N_PER_CLUSTER

    # No errors
    assert error_calls == [], f"Worker emitted error: {error_calls}"

    # Result dict structure
    assert "scenes_enriched" in result, f"result missing 'scenes_enriched': {result}"
    assert (
        result["scenes_enriched"] == total_scenes
    ), f"Expected {total_scenes} enriched scenes, got {result['scenes_enriched']}"
    assert result["mode"] == "fit", f"Expected 'fit' mode, got {result['mode']!r}"
    assert result["clip_id"] is None

    # finished signal was emitted
    assert len(finished_calls) == 1

    # ── Assert DB state ───────────────────────────────────────────────────────
    with sqlite3.connect(str(db_path)) as conn:
        # struct_clip_tags
        tag_rows = conn.execute(
            "SELECT scene_id, role, mood_refined, style_bucket_id, "
            "       enricher_version FROM struct_clip_tags"
        ).fetchall()
        assert len(tag_rows) == total_scenes, (
            f"Expected {total_scenes} struct_clip_tags rows, " f"got {len(tag_rows)}"
        )
        for row in tag_rows:
            scene_id, role, mood_refined, style_bucket_id, enricher_ver = row
            assert role is not None and role != "", f"scene {scene_id}: role is empty"
            assert (
                mood_refined is not None and mood_refined != ""
            ), f"scene {scene_id}: mood_refined is empty"
            assert (
                style_bucket_id is not None
            ), f"scene {scene_id}: style_bucket_id is None"
            assert (
                enricher_ver == "v1"
            ), f"scene {scene_id}: enricher_version is {enricher_ver!r}, expected 'v1'"

        # struct_style_bucket — at least 2 active buckets
        active_buckets = conn.execute(
            "SELECT COUNT(*) FROM struct_style_bucket WHERE active = 1"
        ).fetchone()[0]
        assert (
            active_buckets >= 1
        ), f"Expected >= 1 active struct_style_bucket rows, got {active_buckets}"

        # struct_compat_edge — at least 1 edge
        edge_count = conn.execute("SELECT COUNT(*) FROM struct_compat_edge").fetchone()[
            0
        ]
        assert edge_count > 0, "No struct_compat_edge rows written"

        # rank_in_a must be >= 1
        min_rank = conn.execute(
            "SELECT MIN(rank_in_a) FROM struct_compat_edge"
        ).fetchone()[0]
        assert min_rank >= 1, f"rank_in_a < 1 found: {min_rank}"

        # max rank_in_a ≤ min(top_k=20, N-1).  The builder uses top_k=20 so
        # rank can be 1..20 (1-based).  With N scenes, N-1 is the limit.
        max_rank = conn.execute(
            "SELECT MAX(rank_in_a) FROM struct_compat_edge"
        ).fetchone()[0]
        expected_max = min(20, total_scenes - 1)
        assert (
            max_rank <= expected_max
        ), f"rank_in_a {max_rank} exceeds expected max {expected_max}"

        # AnalysisStatus: clip_id=None → no structure_enrichment rows for real clips
        # (no mark_done called in full-library mode)
        se_rows = conn.execute(
            "SELECT COUNT(*) FROM analysis_status "
            "WHERE step_key = 'structure_enrichment' AND media_type = 'video' "
            "AND status = 'done'"
        ).fetchone()[0]
        assert (
            se_rows == 0
        ), f"Expected 0 done structure_enrichment rows in full-library mode, got {se_rows}"

    # Progress signal was emitted at least at 0 and 100
    pct_values = [p for p, _ in progress_calls]
    assert any(
        p >= 100 for p in pct_values
    ), f"No 100% progress signal emitted. Got: {progress_calls}"


def test_incremental_enrichment_uses_assign_mode(
    enrichment_env: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second run (incremental: clip_id=1) uses assign mode when buckets exist.

    1. First run (full library, fit).
    2. Second run (clip_id=1, no force_refit) → assign mode.
    3. Existing active bucket rows remain active=True.
    4. mode == 'assign' in returned dict.
    """
    from workers.structure_enrichment import StructureEnrichmentWorker

    db_path: Path = enrichment_env["db_path"]
    session_factory = enrichment_env["session_factory"]
    storage_dir: Path = enrichment_env["storage_dir"]

    # ── Run 1: full library ────────────────────────────────────────────────
    worker1 = StructureEnrichmentWorker(
        clip_id=None,
        session_factory=session_factory,
        force_refit=False,
    )
    result1 = worker1.run()
    assert "error" not in result1, f"Run 1 failed: {result1}"
    assert result1["mode"] == "fit"

    # Verify reducer was saved
    reducer_path = storage_dir / "umap_v1.pkl"
    assert reducer_path.exists(), "Reducer pickle not written by fit run"

    # Check active buckets exist
    with sqlite3.connect(str(db_path)) as conn:
        active_before = conn.execute(
            "SELECT COUNT(*) FROM struct_style_bucket WHERE active = 1"
        ).fetchone()[0]
    assert active_before >= 1, "No active buckets after first run"

    # ── Run 2: incremental for clip_id=1 ─────────────────────────────────
    # Monkeypatch analysis_status_service.mark_done so it doesn't try to
    # connect to the production DB (the service uses its own nullpool_session).
    mark_done_calls: list[dict] = []

    import services.analysis_status_service as _sts_mod

    original_mark_done = _sts_mod.mark_done

    def _fake_mark_done(media_type, media_id, step_key, value_summary=None):
        mark_done_calls.append(
            {
                "media_type": media_type,
                "media_id": media_id,
                "step_key": step_key,
                "value_summary": value_summary,
            }
        )

    monkeypatch.setattr(_sts_mod, "mark_done", _fake_mark_done)
    try:
        worker2 = StructureEnrichmentWorker(
            clip_id=1,
            session_factory=session_factory,
            force_refit=False,
        )
        result2 = worker2.run()
    finally:
        monkeypatch.setattr(_sts_mod, "mark_done", original_mark_done)

    assert "error" not in result2, f"Run 2 failed: {result2}"
    assert (
        result2["mode"] == "assign"
    ), f"Expected 'assign' mode on incremental run, got {result2['mode']!r}"
    assert result2["clip_id"] == 1

    # Active buckets must still be active (not deactivated by assign run)
    with sqlite3.connect(str(db_path)) as conn:
        active_after = conn.execute(
            "SELECT COUNT(*) FROM struct_style_bucket WHERE active = 1"
        ).fetchone()[0]
    assert (
        active_after >= active_before
    ), f"Active buckets decreased from {active_before} to {active_after} after assign run"

    # mark_done must have been called exactly once for clip_id=1
    assert (
        len(mark_done_calls) == 1
    ), f"Expected mark_done called once, got {len(mark_done_calls)} calls"
    call = mark_done_calls[0]
    assert call["media_type"] == "video"
    assert call["media_id"] == 1
    assert call["step_key"] == "structure_enrichment"
    assert call["value_summary"]["mode"] == "assign"
