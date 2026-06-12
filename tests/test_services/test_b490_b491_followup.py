"""CRF-005 (B-490/B-491-Followup) — Regressionstests.

B-490 Followup:
  1. ``store_scenes_in_db`` liefert ``stored: bool`` — False bei fehlendem
     VideoClip ODER Projekt-Token-Mismatch (Engine-URL weicht vom
     Pipeline-Start ab). Vorher: stiller Skip, Caller setzte trotzdem
     ``mark_done`` -> Status "done" bei leerer DB.
  2. Caller (``run_deferred_captioning`` / ``run_full_pipeline``) setzen bei
     False ``mark_error("scene_db_storage", ...)`` statt ``mark_done``.
  3. ``set_project()`` lehnt den Engine-Swap mit RuntimeError ab, wenn der
     GlobalTaskManager laufende Tasks meldet (vorher: nur Log-Warnung).

B-491 Followup:
  4. Assign-Modus ohne Reducer-Datei (degradierter Fit persistierte Buckets
     OHNE umap_v1.pkl) -> Single-Bucket-Fallback statt FileNotFoundError.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# B-490 Followup (1): store_scenes_in_db Rueckgabewert
# ---------------------------------------------------------------------------

def test_store_scenes_missing_clip_returns_false(test_engine):
    from services.video_analysis_service import store_scenes_in_db, SceneInfo

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    assert store_scenes_in_db(99999, scenes) is False


def test_store_scenes_existing_clip_returns_true(test_engine, video_clip, db_session):
    from services.video_analysis_service import store_scenes_in_db, SceneInfo
    import database

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=5.0, motion_score=0.3)]
    assert store_scenes_in_db(video_clip.id, scenes) is True
    stored = (
        db_session.query(database.Scene)
        .filter_by(video_clip_id=video_clip.id)
        .all()
    )
    assert len(stored) == 1


def test_store_scenes_project_mismatch_returns_false_writes_nothing(
    test_engine, video_clip, db_session
):
    from services.video_analysis_service import store_scenes_in_db, SceneInfo
    import database

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    result = store_scenes_in_db(
        video_clip.id,
        scenes,
        expected_db_url="sqlite:///C:/ein/anderes/projekt/pb_studio.db",
    )
    assert result is False
    stored = (
        db_session.query(database.Scene)
        .filter_by(video_clip_id=video_clip.id)
        .all()
    )
    assert stored == []


def test_store_scenes_matching_token_returns_true(test_engine, video_clip, db_session):
    """Token == aktive Engine-URL -> Normalpfad unveraendert."""
    import services.video_analysis_service as vas

    scenes = [vas.SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    token = vas._current_db_url()
    assert vas.store_scenes_in_db(video_clip.id, scenes, expected_db_url=token) is True


# ---------------------------------------------------------------------------
# B-490 Followup (2): Caller-Pfade -> mark_error statt mark_done
# ---------------------------------------------------------------------------

def test_run_deferred_captioning_marks_error_on_skip(monkeypatch):
    import services.video_analysis_service as vas

    status_mock = MagicMock()
    monkeypatch.setattr(vas, "analysis_status_service", status_mock)
    monkeypatch.setattr(vas, "analyze_scene_with_caption", lambda scenes: scenes)
    monkeypatch.setattr(vas, "store_scenes_in_db", lambda *a, **k: False)
    enrichment_called = []
    monkeypatch.setattr(
        vas, "_run_structure_enrichment", lambda cid: enrichment_called.append(cid)
    )

    scenes = [vas.SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    result = vas.run_deferred_captioning(7, scenes)

    assert result == scenes
    error_calls = [
        c for c in status_mock.mark_error.call_args_list
        if c.args[:3] == ("video", 7, "scene_db_storage")
    ]
    assert len(error_calls) == 1
    done_storage_calls = [
        c for c in status_mock.mark_done.call_args_list
        if c.args[:3] == ("video", 7, "scene_db_storage")
    ]
    assert done_storage_calls == []
    # Kein Enrichment auf einer DB ohne diese Szenen
    assert enrichment_called == []


def test_run_full_pipeline_marks_error_on_skip(
    monkeypatch, tmp_path, test_engine, video_clip
):
    import services.video_analysis_service as vas

    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"\x00")

    status_mock = MagicMock()
    monkeypatch.setattr(vas, "analysis_status_service", status_mock)

    scenes = [vas.SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    monkeypatch.setattr(vas, "detect_scenes", lambda *a, **k: scenes)
    monkeypatch.setattr(vas, "compute_motion_scores", lambda *a, **k: scenes)
    monkeypatch.setattr(vas, "extract_keyframes", lambda *a, **k: scenes)
    monkeypatch.setattr(vas, "generate_embeddings", lambda *a, **k: scenes)
    monkeypatch.setattr(vas, "analyze_scene_with_caption", lambda s: s)
    monkeypatch.setattr(vas, "store_scenes_in_db", lambda *a, **k: False)
    embeddings_stored = []
    monkeypatch.setattr(
        vas, "store_embeddings",
        lambda *a, **k: embeddings_stored.append(a) or 0,
    )
    enrichment_called = []
    monkeypatch.setattr(
        vas, "_run_structure_enrichment", lambda cid: enrichment_called.append(cid)
    )

    result = vas.run_full_pipeline(str(video_file), video_clip.id)

    error_calls = [
        c for c in status_mock.mark_error.call_args_list
        if c.args[:3] == ("video", video_clip.id, "scene_db_storage")
    ]
    assert len(error_calls) == 1
    done_storage_calls = [
        c for c in status_mock.mark_done.call_args_list
        if c.args[:3] == ("video", video_clip.id, "scene_db_storage")
    ]
    assert done_storage_calls == []
    # B-368-Konsistenz: kein VectorDB-Write, kein Enrichment nach Skip
    assert embeddings_stored == []
    assert enrichment_called == []
    assert result is not None


# ---------------------------------------------------------------------------
# B-490 Followup (3): set_project-Sperre bei laufenden Tasks
# ---------------------------------------------------------------------------

class _FakeTask:
    def __init__(self, status="running", task_id="t1", name="Pipeline"):
        self.status = status
        self.task_id = task_id
        self.name = name


class _FakeTM:
    def __init__(self, tasks):
        self._tasks = tasks

    def get_all_tasks(self):
        return self._tasks


def _patch_task_manager(monkeypatch, tasks):
    import services.task_manager as tm_mod
    fake = _FakeTM(tasks)
    monkeypatch.setattr(
        tm_mod.GlobalTaskManager, "instance", classmethod(lambda cls: fake)
    )


def test_set_project_blocked_by_running_task(monkeypatch, tmp_path):
    from database.session import set_project

    _patch_task_manager(monkeypatch, [_FakeTask(status="running")])
    with pytest.raises(RuntimeError, match="Projektwechsel erst nach"):
        set_project(tmp_path / "proj")


def test_set_project_guard_helper_semantics(monkeypatch):
    from database.session import _running_tasks_block_reason

    # Laufender Task -> Block-Grund
    _patch_task_manager(monkeypatch, [_FakeTask(status="running", name="Render")])
    reason = _running_tasks_block_reason()
    assert reason is not None and "Render" in reason

    # Eigener Task (exclude_task_id) zaehlt nicht
    _patch_task_manager(monkeypatch, [_FakeTask(status="running", task_id="me")])
    assert _running_tasks_block_reason(exclude_task_id="me") is None

    # Nur beendete Tasks -> kein Block
    _patch_task_manager(monkeypatch, [_FakeTask(status="finished")])
    assert _running_tasks_block_reason() is None


def test_set_project_ok_without_running_tasks(monkeypatch, tmp_path):
    """Normalpfad (App-Start / Projekt oeffnen ohne Tasks) darf nicht brechen."""
    import database.session as ses

    _patch_task_manager(monkeypatch, [_FakeTask(status="finished")])
    original_root = ses.APP_ROOT
    proj = tmp_path / "proj_ok"
    proj.mkdir()
    try:
        ses.set_project(proj)
        assert ses.APP_ROOT == proj
        assert (proj / "pb_studio.db").exists()
    finally:
        # Engine auf Repo-Projekt zurueckswappen (Pattern test_ai_audio_real)
        ses.set_project(original_root, force=True)


def test_set_project_force_overrides_block(monkeypatch, tmp_path):
    """force=True (B-051-Rollback-Pfad) swappt trotz laufender Tasks."""
    import database.session as ses

    _patch_task_manager(monkeypatch, [_FakeTask(status="running")])
    original_root = ses.APP_ROOT
    proj = tmp_path / "proj_force"
    proj.mkdir()
    try:
        ses.set_project(proj, force=True)
        assert ses.APP_ROOT == proj
    finally:
        ses.set_project(original_root, force=True)


# ---------------------------------------------------------------------------
# B-491 Followup (4): Assign-Modus ohne Reducer-Datei -> Single-Bucket
# ---------------------------------------------------------------------------

def test_assign_mode_without_reducer_file_single_bucket(monkeypatch, tmp_path):
    import workers.structure_enrichment as se

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
        # Aktiver Bucket aus einem frueheren (degradierten) Fit — OHNE Reducer.
        centroid_blob = np.zeros(10, dtype=np.float32).tobytes()
        conn.execute(
            text(
                "INSERT INTO struct_style_bucket "
                "(name, description, centroid_embedding, member_count, created_at, "
                " enricher_version, active) "
                "VALUES ('bucket_degraded', NULL, :c, 1, '2026-06-12 00:00:00', 'v1', 1)"
            ),
            {"c": centroid_blob},
        )
        # >= REFIT_THRESHOLD struct_clip_tags-Zeilen -> Assign-Modus
        for sid in range(100, 100 + se.REFIT_THRESHOLD + 5):
            conn.execute(
                text(
                    "INSERT INTO struct_clip_tags "
                    "(scene_id, role, role_confidence, mood_refined, mood_confidence, "
                    " style_bucket_id, style_distance, enriched_at, enricher_version) "
                    "VALUES (:sid, 'texture', 1.0, 'neutral', 1.0, 1, 0.0, "
                    "        '2026-06-12 00:00:00', 'v1')"
                ),
                {"sid": sid},
            )

    # Reducer-Datei existiert NICHT (degradierter Fit hat keine geschrieben)
    monkeypatch.setattr(se, "_REDUCER_PATH", tmp_path / "umap_v1.pkl")
    # Step 8 (analysis_status) nicht gegen die echte Projekt-DB laufen lassen
    import services.analysis_status_service as ass
    monkeypatch.setattr(ass, "mark_done", lambda **kw: None)

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

    worker = se.StructureEnrichmentWorker(
        clip_id=1, session_factory=lambda: Session(engine)
    )
    result = worker._do_enrich(
        session=Session(engine),
        classify_role=lambda **_kwargs: ("texture", 1.0),
        MoodAnchorMatcher=_FakeMoodMatcher,
        StyleBucketClusterer=__import__(
            "services.enrichment.style_bucket_clusterer",
            fromlist=["StyleBucketClusterer"],
        ).StyleBucketClusterer,
        CompatGraphBuilder=_FakeCompatGraphBuilder,
        VectorDBService=_FakeVectorDB,
    )

    # Kein Raise, Assign-Modus, degraded-Fallback, Zuordnung auf Bucket 1
    assert "error" not in result
    assert result["mode"] == "assign"
    assert result["degraded"] is True
    assert result["scenes_enriched"] == 1
    with Session(engine) as s:
        row = s.execute(
            text(
                "SELECT style_bucket_id, style_distance FROM struct_clip_tags "
                "WHERE scene_id = 1"
            )
        ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == 0.0
