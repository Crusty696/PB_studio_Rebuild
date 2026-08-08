"""B-778: Gelockte Bestands-Segmente fehlen in der Nutzungs-Cap-Zaehlung.

Livebefund 2026-08-08 (run_id=7, Projekt new_test_august): Timeline-Entry
id=990 (media_id=130, locked=1) ueberlebt Auto-Edit-Apply by design
(B-769). Das B-763-Cap zaehlte aber nur die NEU gewaehlten Slots — Clip
130 stand danach mit max_uses=5 neuen + 1 gelocktem = 6 Segmenten in der
Timeline, ein ungelockter Clip maximal mit 5.

Fix-Vertrag (_seed_usage_counts_from_locked, Seed vor dem Auswahl-Loop):
1. Gelockte video-Eintraege der Kandidaten-Clips zaehlen ab Start ins
   usage_counts-Dict (pro media_id, Mehrfach-Anker = Mehrfach-Zaehlung).
2. Ohne gelockte Eintraege bleibt alles unveraendert (leerer Seed).
3. Nicht gezaehlt: unlocked Eintraege, track='audio', media_ids
   ausserhalb des Kandidaten-Pools.
4. Beide Auswahl-Pfade (Legacy + Studio-Brain) sind abgedeckt, weil der
   Seed das eine geteilte usage_counts-Dict am Init-Punkt vorbelegt.
5. Wirkung im Cap: vorgeseedeter Clip am Limit wird in Stage 3.5
   verworfen, ein Kandidat unter dem Limit gewinnt.
"""
from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from database.models import Base, Project, TimelineEntry, VideoClip
from services.pacing_service import _seed_usage_counts_from_locked


@pytest.fixture()
def seed_engine(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        project = Project(name="b778", path=str(tmp_path))
        session.add(project)
        session.flush()
        for cid in (130, 131, 132):
            session.add(VideoClip(
                id=cid, project_id=project.id,
                file_path=f"c:/x/{cid}.mp4",
            ))
        session.flush()

        def entry(media_id, locked, track="video", start=0.0):
            return TimelineEntry(
                project_id=project.id, track=track, media_id=media_id,
                start_time=start, end_time=start + 5.0, locked=locked,
            )

        session.add_all([
            entry(130, True, start=0.0),      # zaehlt
            entry(130, True, start=10.0),     # zaehlt (Mehrfach-Anker)
            entry(130, False, start=20.0),    # unlocked -> zaehlt nicht
            entry(131, True, start=30.0),     # zaehlt
            entry(132, False, start=40.0),    # unlocked -> zaehlt nicht
            entry(999, True, start=50.0),     # ausserhalb Pool -> nicht
            entry(130, True, track="audio", start=60.0),  # audio -> nicht
        ])
        session.commit()
    yield engine
    engine.dispose()


def test_locked_video_entries_seed_usage_counts(seed_engine):
    seed = _seed_usage_counts_from_locked(seed_engine, [130, 131, 132])
    assert seed == {130: 2, 131: 1}


def test_no_locked_entries_leaves_counts_empty(seed_engine):
    # Pool ohne gelockte Eintraege -> leerer Seed = Bestandsverhalten.
    seed = _seed_usage_counts_from_locked(seed_engine, [132])
    assert seed == {}


def test_seed_error_is_defensive(tmp_path):
    # Engine ohne Tabellen: Seed-Fehler darf Auto-Edit nie stoppen.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    assert _seed_usage_counts_from_locked(engine, [1, 2]) == {}
    engine.dispose()


def test_seed_is_wired_into_shared_usage_counts_init():
    """Vertrag 4: der eine Init-Punkt des geteilten usage_counts-Dicts
    (Legacy- UND Studio-Brain-Pfad) nutzt den Locked-Seed."""
    import inspect

    import services.pacing_service as ps

    src = inspect.getsource(ps._auto_edit_phase3_inner)
    assert "_seed_usage_counts_from_locked(" in src


def test_seeded_clip_at_cap_loses_to_free_clip(tmp_path):
    """Vertrag 5: Cap-Wirkung — vorgeseedeter Clip am Limit verliert."""
    from services.pacing.pipeline import PacingPipeline
    from services.pacing.scorer import AudioContext, ClipFeatures

    rules = tmp_path / "pacing_rules.yaml"
    rules.write_text(
        "section_role_matrix:\n  drop: [hero]\n"
        "key_mood_gate:\n  enabled: false\n  forbidden_moods: []\n"
        "stage1_fallback: soften\n",
        encoding="utf-8",
    )
    pipeline = PacingPipeline(rules_path=str(rules))

    def clip(cid):
        return ClipFeatures(
            clip_id=cid, scene_id=cid * 10, role="hero",
            mood_refined="energetic", style_bucket_id=1, motion_score=0.4,
            embedding=np.ones(4, dtype=np.float32) * 0.5,
        )

    ctx = AudioContext(
        at_timestamp_sec=10.0, at_beat_idx=20, at_section_type="drop",
        at_bpm=140.0, at_energy=0.8, at_key="A min",
        at_key_confidence=0.85, at_harmonic_tension=0.5,
        at_mood_audio="energetic", at_mood_video=None, at_genre="techno",
        at_sub_genre=None, at_spectral_hash="abc12345",
        at_groove_template="four_on_floor", at_lufs=-8.5,
    )
    candidates = [clip(130), clip(131)]
    # Locked-Seed: Clip 130 bereits am Cap (2 Anker, max_uses=2).
    result = pipeline.select_best(
        candidates, ctx, usage_counts={130: 2}, max_uses=2,
    )
    assert result.chosen is not None
    assert result.chosen.clip_id == 131
