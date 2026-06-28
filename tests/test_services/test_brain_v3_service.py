"""Tests fuer BrainV3Service Skeleton (Phase 4)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from database import AudioTrack, Project, TimelineEntry, VideoClip
from sqlalchemy.orm import Session
from services.brain.brain_v3_service import BrainV3Service
from services.brain.context_resolver import CutContext
from services.brain.paths import project_state_db_path
from services.brain.schemas.brain_v3_schemas import (
    FeedbackRequest,
    ResetRequest,
    SuggestRequest,
)
from services.brain.storage.migration_runner import migrate
from services.brain.timeline_state import sync_current_timeline_from_entries


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def test_suggest_returns_top_n_with_brain_scores(isolated_appdata):
    svc = BrainV3Service()
    resp = svc.suggest(SuggestRequest(audio_clip_id=1, video_clip_ids=[1, 2, 3], n_top=2))
    assert len(resp.cuts) == 2
    assert resp.used_brain_v3 is True
    assert resp.explanation["phase4_status"] == "reranker"
    assert all(c.audio_clip_id == 1 for c in resp.cuts)
    assert all("brain_v3_scores" in c.metadata for c in resp.cuts)
    assert all(len(c.metadata["brain_v3_scores"]) == 17 for c in resp.cuts)


def test_feedback_perfect_updates_buckets(isolated_appdata):
    svc = BrainV3Service()
    ctx = CutContext()
    resp = svc.feedback(FeedbackRequest(cut_id=42, rating="perfect"), context=ctx)
    assert resp.cut_id == 42
    assert resp.rating == "perfect"
    assert resp.alpha_delta == 2.0
    assert resp.beta_delta == 0.0
    # 17 axes x 6 levels = 102 buckets
    assert resp.n_buckets_updated == 102


def test_feedback_no_match_updates_beta_only(isolated_appdata):
    svc = BrainV3Service()
    resp = svc.feedback(FeedbackRequest(cut_id=1, rating="no_match"))
    assert resp.alpha_delta == 0.0
    assert resp.beta_delta == 2.0
    assert resp.n_buckets_updated == 102


def test_learning_session_empty_initially(isolated_appdata):
    svc = BrainV3Service(project_root=isolated_appdata / "empty_project")
    resp = svc.learning_session(n=15)
    assert resp.requested_n == 15
    assert resp.available_n == 0
    assert resp.samples == []


def test_learning_session_returns_samples_after_clicks(isolated_appdata):
    svc = BrainV3Service()
    for _ in range(2):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    for _ in range(2):
        svc.feedback(FeedbackRequest(cut_id=2, rating="no_match"))
    resp = svc.learning_session(n=10)
    assert resp.requested_n == 10
    assert resp.available_n > 0
    assert all(0.0 <= s.uncertainty <= 1.0 for s in resp.samples)


def test_learning_session_prefers_real_timeline_cuts_with_preview_paths(
    isolated_appdata,
    db_session,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    proxy_file = tmp_path / "clip_proxy.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")
    proxy_file.write_bytes(b"proxy")

    project = Project(name="Preview", path=str(project_root), resolution="1920x1080", fps=30)
    db_session.add(project)
    db_session.commit()
    audio = AudioTrack(
        project_id=project.id,
        file_path=str(audio_file),
        title="Mix",
        duration=180.0,
    )
    video = VideoClip(
        project_id=project.id,
        file_path=str(video_file),
        proxy_path=str(proxy_file),
        duration=12.0,
    )
    db_session.add_all([audio, video])
    db_session.commit()

    state_db = project_state_db_path(project_root)
    migrate(
        state_db,
        Path("services/brain_v3/storage/sql_migrations/state"),
    )
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO timelines(id, name, audio_clip_id, created_at, is_current) "
            "VALUES (1, 'current', ?, '2026-05-07T00:00:00', 1)",
            (audio.id,),
        )
        conn.execute(
            "INSERT INTO timeline_cuts("
            "id, timeline_id, position_idx, clip_id, start_time, end_time, clip_start, "
            "brain_v3_scores_json, metadata_json"
            ") VALUES (11, 1, 0, ?, 24.5, 30.5, 3.25, ?, ?)",
            (
                str(video.id),
                '{"confidence": 0.82}',
                '{"brain_v3_confidence": 0.82}',
            ),
        )
        conn.commit()

    @contextmanager
    def _session_factory():
        yield db_session

    svc = BrainV3Service(project_root=project_root, session_factory=_session_factory)
    resp = svc.learning_session(n=15)

    assert resp.available_n == 1
    sample = resp.samples[0]
    assert sample.cut_id == 11
    assert sample.clip_id == video.id
    assert sample.audio_preview_path == str(audio_file)
    assert sample.video_preview_path == str(proxy_file)
    assert sample.audio_position_s == 24.5
    assert sample.video_position_s == 3.25
    assert sample.preview_duration_s == 6.0
    assert sample.has_preview is True
    assert sample.uncertainty == pytest.approx(0.18)


def test_learning_session_preview_resolver_survives_closed_session_factory(
    isolated_appdata,
    test_engine,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")
    with Session(test_engine) as session:
        project = Project(name="Closed", path=str(project_root), resolution="1920x1080", fps=30)
        session.add(project)
        session.commit()
        audio = AudioTrack(project_id=project.id, file_path=str(audio_file), duration=120)
        video = VideoClip(project_id=project.id, file_path=str(video_file), duration=10)
        session.add_all([audio, video])
        session.commit()
        audio_id = audio.id
        video_id = video.id

    state_db = project_state_db_path(project_root)
    migrate(state_db, Path("services/brain_v3/storage/sql_migrations/state"))
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO timelines(id, name, audio_clip_id, created_at, is_current) "
            "VALUES (1, 'current', ?, '2026-05-07T00:00:00', 1)",
            (audio_id,),
        )
        conn.execute(
            "INSERT INTO timeline_cuts(id, timeline_id, position_idx, clip_id, start_time, end_time) "
            "VALUES (22, 1, 0, ?, 1.0, 3.0)",
            (str(video_id),),
        )
        conn.commit()

    @contextmanager
    def _session_factory():
        with Session(test_engine) as session:
            yield session

    sample = BrainV3Service(
        project_root=project_root,
        session_factory=_session_factory,
    ).learning_session(n=1).samples[0]
    assert sample.audio_preview_path == str(audio_file)
    assert sample.video_preview_path == str(video_file)


def test_sync_current_timeline_from_entries_creates_learning_preview_state(
    isolated_appdata,
    db_session,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")

    project = Project(name="Sync", path=str(project_root), resolution="1920x1080", fps=30)
    db_session.add(project)
    db_session.commit()
    audio = AudioTrack(project_id=project.id, file_path=str(audio_file), duration=120)
    video = VideoClip(project_id=project.id, file_path=str(video_file), duration=10)
    db_session.add_all([audio, video])
    db_session.commit()

    entries = [
        type("Entry", (), {
            "id": 1,
            "track": "audio",
            "media_id": audio.id,
            "start_time": 0.0,
            "end_time": 120.0,
            "source_start": 0.0,
            "source_end": 120.0,
        })(),
        type("Entry", (), {
            "id": 2,
            "track": "video",
            "media_id": video.id,
            "start_time": 16.0,
            "end_time": 20.0,
            "source_start": 2.0,
            "source_end": 6.0,
        })(),
    ]

    assert sync_current_timeline_from_entries(project_root, entries) is True

    @contextmanager
    def _session_factory():
        yield db_session

    svc = BrainV3Service(project_root=project_root, session_factory=_session_factory)
    sample = svc.learning_session(n=15).samples[0]
    assert sample.audio_preview_path == str(audio_file)
    assert sample.video_preview_path == str(video_file)
    assert sample.audio_position_s == 16.0
    assert sample.video_position_s == 2.0


def test_sync_current_timeline_from_entries_replaces_stale_current_state(
    isolated_appdata,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_db = project_state_db_path(project_root)
    migrate(state_db, Path("services/brain_v3/storage/sql_migrations/state"))
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO timelines(id, name, audio_clip_id, created_at, is_current) "
            "VALUES (1, 'stale', 5, '2026-05-22T00:00:00', 1)"
        )
        conn.execute(
            "INSERT INTO timeline_cuts(id, timeline_id, position_idx, clip_id, start_time, end_time) "
            "VALUES (11, 1, 0, '9', 0.0, 5.0)"
        )
        conn.commit()

    entries = [
        type("Entry", (), {
            "track": "audio",
            "media_id": 2,
            "start_time": 0.0,
            "end_time": 120.0,
            "source_start": 0.0,
            "source_end": 120.0,
        })(),
        type("Entry", (), {
            "track": "video",
            "media_id": 72,
            "start_time": 10.322,
            "end_time": 15.522,
            "source_start": 0.0,
            "source_end": 5.2,
        })(),
    ]

    assert sync_current_timeline_from_entries(project_root, entries) is True

    with sqlite3.connect(state_db) as conn:
        stale_current = conn.execute(
            "SELECT is_current FROM timelines WHERE id=1"
        ).fetchone()[0]
        current = conn.execute(
            """
            SELECT t.audio_clip_id, c.clip_id, c.start_time, c.metadata_json
            FROM timelines t
            JOIN timeline_cuts c ON c.timeline_id=t.id
            WHERE t.is_current=1
            """
        ).fetchone()

    assert stale_current == 0
    assert current[0] == 2
    assert current[1] == "72"
    assert current[2] == 10.322
    assert '"brain_v3_confidence": 0.5' in current[3]


def test_sync_current_timeline_detects_source_offset_and_end_change(
    isolated_appdata,
    tmp_path,
):
    # B-373: change to source offset or end_time on the same clip + same
    # timeline start must be recognised as a sync change.
    project_root = tmp_path / "project"
    project_root.mkdir()

    def _entries(src_start, end):
        return [
            type("Entry", (), {
                "track": "audio", "media_id": 2, "start_time": 0.0,
                "end_time": 120.0, "source_start": 0.0, "source_end": 120.0,
            })(),
            type("Entry", (), {
                "track": "video", "media_id": 72, "start_time": 10.0,
                "end_time": end, "source_start": src_start,
                "source_end": src_start + 5.0,
            })(),
        ]

    # initial create
    assert sync_current_timeline_from_entries(project_root, _entries(0.0, 15.0)) is True
    # identical -> no change (idempotent)
    assert sync_current_timeline_from_entries(project_root, _entries(0.0, 15.0)) is False
    # same clip + same start, changed source offset -> must re-sync
    assert sync_current_timeline_from_entries(project_root, _entries(3.0, 15.0)) is True
    assert sync_current_timeline_from_entries(project_root, _entries(3.0, 15.0)) is False
    # changed end_time (duration) -> must re-sync
    assert sync_current_timeline_from_entries(project_root, _entries(3.0, 18.0)) is True


def test_learning_session_recovers_from_stale_state_audio_id(
    isolated_appdata,
    db_session,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "current_mix.mp3"
    video_file = tmp_path / "clip.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")

    project = Project(name="StaleAudio", path=str(project_root), resolution="1920x1080", fps=30)
    db_session.add(project)
    db_session.commit()
    audio = AudioTrack(project_id=project.id, file_path=str(audio_file), duration=120)
    video = VideoClip(project_id=project.id, file_path=str(video_file), duration=10)
    db_session.add_all([audio, video])
    db_session.commit()
    db_session.add(
        TimelineEntry(
            project_id=project.id,
            track="audio",
            media_id=audio.id,
            start_time=0.0,
            end_time=120.0,
        )
    )
    db_session.commit()

    state_db = project_state_db_path(project_root)
    migrate(state_db, Path("services/brain_v3/storage/sql_migrations/state"))
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO timelines(id, name, audio_clip_id, created_at, is_current) "
            "VALUES (1, 'stale', 999999, '2026-05-22T00:00:00', 1)"
        )
        conn.execute(
            "INSERT INTO timeline_cuts(id, timeline_id, position_idx, clip_id, start_time, end_time) "
            "VALUES (33, 1, 0, ?, 4.0, 8.0)",
            (str(video.id),),
        )
        conn.commit()

    @contextmanager
    def _session_factory():
        yield db_session

    sample = BrainV3Service(
        project_root=project_root,
        session_factory=_session_factory,
    ).learning_session(n=1).samples[0]
    assert sample.audio_preview_path == str(audio_file)
    assert sample.video_preview_path == str(video_file)


def test_learning_session_uses_original_video_when_proxy_missing(
    isolated_appdata,
    db_session,
    tmp_path,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    missing_proxy = tmp_path / "missing_proxy.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")

    project = Project(name="MissingProxy", path=str(project_root), resolution="1920x1080", fps=30)
    db_session.add(project)
    db_session.commit()
    audio = AudioTrack(project_id=project.id, file_path=str(audio_file), duration=120)
    video = VideoClip(
        project_id=project.id,
        file_path=str(video_file),
        proxy_path=str(missing_proxy),
        duration=10,
    )
    db_session.add_all([audio, video])
    db_session.commit()

    state_db = project_state_db_path(project_root)
    migrate(state_db, Path("services/brain_v3/storage/sql_migrations/state"))
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO timelines(id, name, audio_clip_id, created_at, is_current) "
            "VALUES (1, 'current', ?, '2026-05-22T00:00:00', 1)",
            (audio.id,),
        )
        conn.execute(
            "INSERT INTO timeline_cuts(id, timeline_id, position_idx, clip_id, start_time, end_time) "
            "VALUES (44, 1, 0, ?, 4.0, 8.0)",
            (str(video.id),),
        )
        conn.commit()

    @contextmanager
    def _session_factory():
        yield db_session

    sample = BrainV3Service(
        project_root=project_root,
        session_factory=_session_factory,
    ).learning_session(n=1).samples[0]
    assert sample.video_preview_path == str(video_file)


def test_stats_after_init_shows_cold_start(isolated_appdata):
    svc = BrainV3Service()
    s = svc.stats()
    assert s.total_clicks >= 0
    # Initial = no learned axes
    assert s.cold_start_axes == 17
    assert s.learned_axes == 0


def test_stats_after_feedback_shows_some_learning(isolated_appdata):
    svc = BrainV3Service()
    # 10 perfect-Klicks fuer denselben Default-Context = 10 Samples pro Bucket
    for _ in range(10):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    s = svc.stats()
    # 17 Achsen sollten alle gelernt sein (10 x 2.0 alpha = 20 Samples >= 10)
    assert s.learned_axes == 17
    assert s.cold_start_axes == 0
    assert len(s.top_positive_buckets) > 0


def test_reset_two_step_flow(isolated_appdata):
    svc = BrainV3Service()
    # Step 1: token request
    r1 = svc.reset(ResetRequest())
    assert r1.status == "token_required"
    assert r1.confirmation_token is not None
    # Step 2: confirm
    r2 = svc.reset(ResetRequest(confirmation_token=r1.confirmation_token))
    assert r2.status == "reset_done"
    assert "axis_weights" in r2.cleared_tables
    assert "pattern_correlations" in r2.cleared_tables
    assert "media_embedding_index" not in r2.cleared_tables  # default false


def test_reset_wrong_token_rejected(isolated_appdata):
    svc = BrainV3Service()
    svc.reset(ResetRequest())  # set token
    bad = svc.reset(ResetRequest(confirmation_token="wrong-token"))
    assert bad.status == "token_required"


def test_reset_with_embedding_cache_flag(isolated_appdata):
    svc = BrainV3Service()
    r1 = svc.reset(ResetRequest(also_embedding_cache=True))
    r2 = svc.reset(ResetRequest(
        confirmation_token=r1.confirmation_token,
        also_embedding_cache=True,
    ))
    assert r2.status == "reset_done"
    assert "media_embedding_index" in r2.cleared_tables


def test_reset_actually_clears_axis_weights(isolated_appdata):
    svc = BrainV3Service()
    svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    s_pre = svc.stats()
    assert s_pre.total_clicks > 0
    r1 = svc.reset(ResetRequest())
    svc.reset(ResetRequest(confirmation_token=r1.confirmation_token))
    s_post = svc.stats()
    assert s_post.total_clicks == 0
    assert s_post.learned_axes == 0


def test_health_returns_in_process_status(isolated_appdata):
    svc = BrainV3Service()

    health = svc.health()

    assert health.ok is True
    assert health.weights_ok is True
    assert health.patterns_ok is True
    assert health.disk_space_mb > 0
    assert health.total_clicks >= 0
    assert "PB_Studio" in health.brain_v3_dir
    assert "brain_v3" in health.brain_v3_dir
    assert "brain_v2" not in health.brain_v3_dir.lower()
