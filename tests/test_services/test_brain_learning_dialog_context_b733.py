"""B-733 — der Lern-Dialog schickte jedem Feedback einen leeren Kontext.

``ui/widgets/brain_v3_learning_dialog.py`` uebergab ``CutContext()``. Damit
landete JEDES Feedback aus der Lern-Session auf demselben Default-Schluessel
und der 6-stufige Backoff im WeightStore lief leer (Live-Beleg: in der echten
weights.db existieren nur 2 distinkte Level-5-Schluessel).

Der Vorbefund lautete, ``LearningSampleCut`` fuehre weder Section noch Mood —
das stimmt fuer das Schema. Die QUELLE existiert aber:
``timeline_cuts.start_time`` (state.db) + ``structure_segments`` +
``audio_tracks.mood/.bpm`` (Haupt-DB). Genau diese Aufloesung testet diese
Datei.

Ehrlich offen: ``video_motion_class`` hat KEINE Quelle pro Cut in state.db und
bleibt deshalb bewusst auf dem neutralen Default statt geraten zu werden.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import database
from services.brain.timeline_state import (
    ensure_state_db,
    load_learning_cut_contexts,
)


@pytest.fixture
def session_factory(test_engine):
    @contextmanager
    def _factory():
        with Session(test_engine) as s:
            yield s

    return _factory


def _seed_state_db(project_root: Path, audio_clip_id: int,
                   cuts: list[tuple[float, str | None]]) -> list[int]:
    """Legt eine current-Timeline mit ``cuts`` (start_time, segment_type) an."""
    db_path = ensure_state_db(project_root)
    ids: list[int] = []
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO timelines(name, audio_clip_id, created_at, "
            "config_json, is_current) VALUES (?, ?, ?, ?, 1)",
            ("t", audio_clip_id, datetime.now(timezone.utc).isoformat(), "{}"),
        )
        timeline_id = int(cur.lastrowid)
        for idx, (start, segment_type) in enumerate(cuts):
            c = conn.execute(
                "INSERT INTO timeline_cuts(timeline_id, position_idx, clip_id, "
                "start_time, end_time, clip_start, segment_type) "
                "VALUES (?, ?, ?, ?, ?, 0, ?)",
                (timeline_id, idx, "1", start, start + 2.0, segment_type),
            )
            ids.append(int(c.lastrowid))
        conn.commit()
    return ids


def _seed_structure(db_session, audio_track):
    audio_track.mood = "dark"
    audio_track.bpm = 145.0
    for start, end, label, energy in (
        (0.0, 30.0, "INTRO", 0.1),
        (30.0, 60.0, "BUILDUP", 0.5),
        (60.0, 90.0, "DROP", 0.95),
        (90.0, 120.0, "BREAKDOWN", 0.3),
    ):
        db_session.add(database.StructureSegment(
            audio_track_id=audio_track.id,
            start_time=start, end_time=end, label=label, energy=energy,
        ))
    db_session.commit()


def test_contexts_differ_per_cut(tmp_path, db_session, audio_track,
                                session_factory):
    """Kernbeweis: verschiedene Cuts bekommen verschiedene Backoff-Schluessel."""
    _seed_structure(db_session, audio_track)
    ids = _seed_state_db(tmp_path, audio_track.id, [
        (5.0, None),     # INTRO, ganz am Anfang
        (45.0, None),    # BUILDUP, Mitte
        (88.0, None),    # DROP, Ende
    ])

    ctxs = load_learning_cut_contexts(
        project_root=tmp_path, session_factory=session_factory, cut_ids=ids,
    )
    assert set(ctxs) == set(ids), f"Kontexte fehlen: {sorted(set(ids) - set(ctxs))}"

    from services.brain.context_resolver import context_keys

    level5 = {context_keys(c)[5] for c in ctxs.values()}
    assert len(level5) == 3, (
        f"Alle Cuts auf demselben Level-5-Schluessel -> Backoff laeuft leer: "
        f"{level5}"
    )

    intro, buildup, drop = (ctxs[i] for i in ids)
    assert intro.audio_section_type == "intro"
    assert buildup.audio_section_type == "build"   # BUILDUP -> build
    assert drop.audio_section_type == "drop"
    # Mood + Pace kommen aus dem echten AudioTrack
    assert drop.audio_mood == "dark"
    assert drop.video_pace_class == "fast"          # 145 BPM
    # Subtrack-Position aus den echten Segment-Grenzen
    assert intro.audio_subtrack_position == "start"   # 5 von 0..30
    assert buildup.audio_subtrack_position == "middle"  # 45 von 30..60
    assert drop.audio_subtrack_position == "end"       # 88 von 60..90
    # Energie tertil-quantisiert ueber die echten Segment-Energien
    assert intro.audio_energy_level == "low"
    assert drop.audio_energy_level == "high"


def test_segment_type_column_wins_over_structure(tmp_path, db_session,
                                                 audio_track, session_factory):
    """Steht die Section am Cut selbst, wird sie genommen."""
    _seed_structure(db_session, audio_track)
    ids = _seed_state_db(tmp_path, audio_track.id, [(5.0, "OUTRO")])

    ctxs = load_learning_cut_contexts(
        project_root=tmp_path, session_factory=session_factory, cut_ids=ids,
    )
    assert ctxs[ids[0]].audio_section_type == "outro"


def test_no_structure_means_no_invented_context(tmp_path, db_session,
                                                audio_track, session_factory):
    """Ohne Quelle wird KEIN Kontext erfunden — der Cut fehlt im Ergebnis.

    Der Dialog kennzeichnet ihn dann als '[ohne Kontext]'.
    """
    ids = _seed_state_db(tmp_path, audio_track.id, [(5.0, None)])

    ctxs = load_learning_cut_contexts(
        project_root=tmp_path, session_factory=session_factory, cut_ids=ids,
    )
    assert ctxs == {}


def test_motion_stays_neutral_because_there_is_no_source(tmp_path, db_session,
                                                        audio_track,
                                                        session_factory):
    """Dokumentiert die bewusst offene Luecke, damit sie nicht still zudriftet."""
    _seed_structure(db_session, audio_track)
    ids = _seed_state_db(tmp_path, audio_track.id, [(70.0, None)])

    ctxs = load_learning_cut_contexts(
        project_root=tmp_path, session_factory=session_factory, cut_ids=ids,
    )
    assert ctxs[ids[0]].video_motion_class == "medium"


def test_empty_state_db_returns_empty(tmp_path, session_factory):
    ensure_state_db(tmp_path)
    assert load_learning_cut_contexts(
        project_root=tmp_path, session_factory=session_factory,
    ) == {}
