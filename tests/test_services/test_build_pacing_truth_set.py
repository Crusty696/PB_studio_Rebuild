"""Tests fuer scripts/build_pacing_truth_set.py.

Verifiziert dass mem_decision-Rows mit user_verdict='good'/'bad'
korrekt ins Truth-Set-JSON-Format exportiert werden — und dass das
Output-Schema von ``scripts/tune_pacing_reward.py`` gelesen werden
kann (Smoke-Test).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

# Repo-Root in sys.path damit scripts/ importierbar ist
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build_pacing_truth_set import _row_to_truth_entry, export_truth_set


def _build_test_db(tmp_path: Path) -> Path:
    """Mini-DB mit audio_tracks + mem_pacing_run + mem_decision (mit
    Verdicts) — minimum schema fuer den Export-Test."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "test.db"
    bootstrap_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with bootstrap_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE audio_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE video_clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_clip_id INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                label TEXT,
                energy REAL,
                FOREIGN KEY (video_clip_id) REFERENCES video_clips(id)
            )
        """))
    bootstrap_engine.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")

    # Seed: 1 audio_track + 1 run + 5 mem_decision rows (3 good, 1 bad, 1 neutral)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at)
            VALUES (1, '/abs/path/track.wav', 'track.wav', 'sha-aaa', 'ready', :ts)
        """), {"ts": now})
        conn.execute(text("""
            INSERT INTO video_clips (id, file_path, original_filename, sha256, status, created_at)
            VALUES (1, '/abs/v.mp4', 'v.mp4', 'sha-vvv', 'ready', :ts)
        """), {"ts": now})
        conn.execute(text("""
            INSERT INTO scenes (id, video_clip_id, start_time, end_time, label, energy)
            VALUES (1, 1, 0.0, 5.0, 'Scene 0', 0.5)
        """))
        conn.execute(text("""
            INSERT INTO mem_pacing_run
                (id, audio_track_id, started_at, is_dj_mix, total_duration_sec,
                 total_cuts, agent_version, weights_profile)
            VALUES (1, 1, :ts, 0, 120.0, 5, 'test', 'default')
        """), {"ts": now})

        for seq, verdict in enumerate([
            "good", "good", "bad", "good", None,
        ]):
            conn.execute(text("""
                INSERT INTO mem_decision
                    (run_id, sequence_idx, at_timestamp_sec, at_section_type,
                     at_bpm, at_genre, at_enricher_version, at_energy,
                     scene_id, clip_role, clip_mood_refined,
                     clip_style_bucket_id, clip_motion_score,
                     agent_score, agent_rationale, user_verdict)
                VALUES (1, :seq, :ts_sec, 'verse', 128.0, 'house',
                        'v1', :energy,
                        1, 'hero', 'euphoric',
                        :bucket, 0.7,
                        0.85, '{}', :verdict)
            """), {
                "seq": seq,
                "ts_sec": float(seq) * 2.0,
                "energy": 0.6,
                "bucket": 1,
                "verdict": verdict,
            })

    return db_path


# --------------------------------------------------------------------------
# _row_to_truth_entry
# --------------------------------------------------------------------------

def test_row_to_truth_entry_basic_fields() -> None:
    row = {
        "run_id": 42,
        "sequence_idx": 7,
        "at_timestamp_sec": 30.5,
        "at_energy": 0.72,
        "at_section_type": "verse",
        "scene_id": 100,
        "clip_motion_score": 0.32,
        "clip_style_bucket_id": 7,
        "agent_rationale": '{"vocal_energy": 0.81, "drum_energy": 0.45}',
        "user_verdict": "good",
        "track_file_path": "/abs/path/track.wav",
    }
    entry = _row_to_truth_entry(row)
    assert entry["run_id"] == "42"
    assert entry["cut_id"] == 7
    assert entry["timestamp_ms"] == 30500
    assert entry["track_id"] == "/abs/path/track.wav"
    assert entry["verdict"] == "good"
    # Audio-Features
    assert entry["audio_features"]["rms"] == pytest.approx(0.72)
    assert entry["audio_features"]["section_type"] == "verse"
    assert entry["audio_features"]["vocal_energy"] == pytest.approx(0.81)
    assert entry["audio_features"]["drum_energy"] == pytest.approx(0.45)
    # Video-Features
    assert entry["video_features"]["motion_score"] == pytest.approx(0.32)
    assert entry["video_features"]["mood_cluster"] == 7


def test_row_to_truth_entry_handles_dict_rationale() -> None:
    """JSON-Column kann auch direkt als dict zurueckkommen (SQLAlchemy)."""
    row = {
        "run_id": 1, "sequence_idx": 0, "at_timestamp_sec": 0.0,
        "at_energy": 0.5, "at_section_type": "drop",
        "scene_id": 1, "clip_motion_score": 0.5, "clip_style_bucket_id": 0,
        "agent_rationale": {"shot_type": "close_up", "cosine_sim_to_audio_mood": 0.8},
        "user_verdict": "bad", "track_file_path": "/x.wav",
    }
    entry = _row_to_truth_entry(row)
    assert entry["video_features"]["shot_type"] == "close_up"
    assert entry["video_features"]["cosine_sim_to_audio_mood"] == pytest.approx(0.8)


def test_row_to_truth_entry_handles_none_rationale() -> None:
    """Wenn rationale leer/kaputt ist, fallen Features auf 0.5/None."""
    row = {
        "run_id": 1, "sequence_idx": 0, "at_timestamp_sec": 0.0,
        "at_energy": None, "at_section_type": None,
        "scene_id": 1, "clip_motion_score": None, "clip_style_bucket_id": None,
        "agent_rationale": None,
        "user_verdict": "good", "track_file_path": None,
    }
    entry = _row_to_truth_entry(row)
    assert entry["audio_features"]["rms"] == 0.5
    assert entry["audio_features"]["section_type"] == "verse"
    assert entry["video_features"]["motion_score"] == 0.5
    assert entry["video_features"]["mood_cluster"] == 0
    assert entry["video_features"]["shot_type"] is None
    assert entry["track_id"] == "unknown"


# --------------------------------------------------------------------------
# export_truth_set (End-to-End mit echter SQLite)
# --------------------------------------------------------------------------

def test_export_truth_set_only_includes_good_bad(tmp_path: Path) -> None:
    db_path = _build_test_db(tmp_path)
    output = tmp_path / "truth_set.json"

    n = export_truth_set(db_path=db_path, output_path=output, min_cuts=0)
    # 5 rows: 3 good, 1 bad, 1 neutral → 4 included by default
    assert n == 4

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert len(payload["data"]) == 4
    assert all(e["verdict"] in {"good", "bad"} for e in payload["data"])


def test_export_truth_set_include_neutral_flag(tmp_path: Path) -> None:
    db_path = _build_test_db(tmp_path)
    output = tmp_path / "truth_set.json"

    n = export_truth_set(
        db_path=db_path, output_path=output, min_cuts=0, include_neutral=True,
    )
    # All 5 rows
    assert n == 5
    payload = json.loads(output.read_text(encoding="utf-8"))
    verdicts = [e["verdict"] for e in payload["data"]]
    assert "neutral" in verdicts


def test_export_truth_set_missing_db_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "no_such_db.sqlite"
    with pytest.raises(FileNotFoundError):
        export_truth_set(db_path=bogus, output_path=tmp_path / "out.json")


# --------------------------------------------------------------------------
# Integration: Output ist von tune_pacing_reward.py lesbar
# --------------------------------------------------------------------------

def test_output_format_is_compatible_with_tune_pacing_reward(tmp_path: Path) -> None:
    """Smoke: ``tune_pacing_reward._load_truth_set`` und
    ``_row_to_components`` muessen das Output-File konsumieren koennen."""
    from scripts.tune_pacing_reward import _load_truth_set, _row_to_components

    db_path = _build_test_db(tmp_path)
    output = tmp_path / "truth_set.json"
    export_truth_set(db_path=db_path, output_path=output, min_cuts=0)

    loaded = _load_truth_set(output)
    # _load_truth_set returnt das ganze payload-dict — wir brauchen .data
    rows = loaded.get("data", []) if isinstance(loaded, dict) else loaded
    assert len(rows) == 4
    # Pruefe dass _row_to_components nicht crasht
    for row in rows:
        components = _row_to_components(row)
        assert hasattr(components, "r_energy")
        assert 0.0 <= components.r_energy <= 1.0
