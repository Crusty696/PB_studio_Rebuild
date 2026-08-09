"""B-781 — Achsen-Credit muss den Lern-Dialog-Pfad erreichen.

Vertraege (alle vier aus dem Bugfile B-781):
  (a) ``sync_current_timeline_from_entries`` schreibt die ECHTEN
      Achsen-Scores der Entscheidung nach ``timeline_cuts.brain_v3_scores_json``
      statt des konstanten Platzhalters ``{"confidence": 0.5}``.
  (b) Der Lern-Dialog leitet daraus ``axis_contributions`` ab und gibt sie an
      das Feedback-Popup weiter.
  (c) Feedback ueber diesen Pfad landet im ``credit_mode='weighted'``-Pfad mit
      weniger als 18 credited Achsen (statt uniform ueber 108 Buckets).
  (d) Bestandszeilen mit nur ``{"confidence": 0.5}`` fallen sauber auf den
      Uniform-Pfad zurueck — kein Crash.

CPU-only, kein interaktives ``.exec()``, Qt offscreen.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from database import AudioTrack, Project, Scene, VideoClip
from services.brain.brain_v3_service import BrainV3Service
from services.brain.schemas.brain_v3_schemas import FeedbackRequest
from services.brain.timeline_state import (
    load_learning_axis_contributions,
    state_db_path,
    sync_current_timeline_from_entries,
)


# Achsen-Sub-Scores, wie sie services/pacing/pipeline.py:675 in
# mem_decision.agent_rationale["brain_v3_scores"] schreibt.
REAL_AXIS_SCORES = {
    "energy_weight": 0.8,
    "role_match_weight": 0.2,
    "beat_weight": 0.0,
}

CUT_START_S = 16.0


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def _create_mem_tables(session) -> None:
    """mem_pacing_run/mem_decision existieren nur als Alembic-Revision.

    Die In-Memory-Engine der Tests baut ausschliesslich ORM-Tabellen, die
    beiden Memory-Tabellen fehlen dort. Nur die Spalten, die der B-781-Pfad
    tatsaechlich liest bzw. die NOT NULL sind.
    """
    session.execute(_sql(
        "CREATE TABLE IF NOT EXISTS mem_pacing_run ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " audio_track_id INTEGER NOT NULL,"
        " started_at TEXT NOT NULL)"
    ))
    session.execute(_sql(
        "CREATE TABLE IF NOT EXISTS mem_decision ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " run_id INTEGER NOT NULL,"
        " sequence_idx INTEGER NOT NULL,"
        " at_timestamp_sec REAL NOT NULL,"
        " scene_id INTEGER NOT NULL,"
        " agent_rationale TEXT NOT NULL)"
    ))
    session.commit()


def _sql(statement: str):
    from sqlalchemy import text as _text

    return _text(statement)


def _seed_project(db_session, tmp_path: Path):
    """Projekt + Audio + Video + Scene + Pacing-Entscheidung mit echten Scores."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")

    project = Project(
        name="B781", path=str(project_root), resolution="1920x1080", fps=30,
    )
    db_session.add(project)
    db_session.commit()
    audio = AudioTrack(
        project_id=project.id, file_path=str(audio_file), duration=120,
    )
    video = VideoClip(
        project_id=project.id, file_path=str(video_file), duration=30,
    )
    db_session.add_all([audio, video])
    db_session.commit()
    scene = Scene(video_clip_id=video.id, start_time=0.0, end_time=4.0)
    db_session.add(scene)
    db_session.commit()

    _create_mem_tables(db_session)
    db_session.execute(
        _sql(
            "INSERT INTO mem_pacing_run(audio_track_id, started_at) "
            "VALUES (:aid, '2026-08-09T10:00:00')"
        ),
        {"aid": audio.id},
    )
    run_id = db_session.execute(_sql("SELECT id FROM mem_pacing_run")).scalar()
    db_session.execute(
        _sql(
            "INSERT INTO mem_decision("
            " run_id, sequence_idx, at_timestamp_sec, scene_id, agent_rationale"
            ") VALUES (:rid, 0, :ts, :sid, :rat)"
        ),
        {
            "rid": int(run_id),
            "ts": CUT_START_S,
            "sid": int(scene.id),
            "rat": json.dumps({"brain_v3_scores": REAL_AXIS_SCORES}),
        },
    )
    db_session.commit()

    entries = [
        type("Entry", (), {
            "id": 1, "track": "audio", "media_id": audio.id,
            "start_time": 0.0, "end_time": 120.0,
            "source_start": 0.0, "source_end": 120.0,
        })(),
        type("Entry", (), {
            "id": 2, "track": "video", "media_id": video.id,
            "start_time": CUT_START_S, "end_time": CUT_START_S + 4.0,
            "source_start": 0.0, "source_end": 4.0,
        })(),
    ]
    return project_root, entries


def _read_scores_json(project_root: Path) -> str:
    with sqlite3.connect(state_db_path(project_root)) as conn:
        return conn.execute(
            "SELECT c.brain_v3_scores_json FROM timeline_cuts c "
            "JOIN timelines t ON t.id = c.timeline_id WHERE t.is_current = 1"
        ).fetchone()[0]


# ── (a) Sync schreibt echte Achsen-Scores ────────────────────────────────
def test_sync_writes_real_axis_scores_not_placeholder(
    isolated_appdata, db_session, tmp_path,
):
    project_root, entries = _seed_project(db_session, tmp_path)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_from_entries(
        project_root, entries, session_factory=_sf,
    ) is True

    raw = _read_scores_json(project_root)
    data = json.loads(raw)
    assert data.get("brain_v3_scores") == REAL_AXIS_SCORES, (
        f"timeline_cuts.brain_v3_scores_json ohne echte Achsen-Scores: {raw!r}"
    )


# ── (b) Dialog-Payload enthaelt axis_contributions ───────────────────────
def test_learning_dialog_passes_axis_contributions_to_popup(
    isolated_appdata, db_session, tmp_path, monkeypatch,
):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QListWidgetItem

    QApplication.instance() or QApplication([])

    project_root, entries = _seed_project(db_session, tmp_path)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_from_entries(
        project_root, entries, session_factory=_sf,
    ) is True

    contribs = load_learning_axis_contributions(project_root=project_root)
    assert contribs, "Kein Achsen-Beitrag aus timeline_cuts abgeleitet"
    cut_id = next(iter(contribs))

    import ui.widgets.brain_v3_learning_dialog as dlg_mod

    captured: dict = {}

    class _CapturePopup:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def exec(self):
            return 0

        @property
        def feedback_submitted(self):
            class _Sig:
                @staticmethod
                def connect(_slot):
                    return None
            return _Sig()

    monkeypatch.setattr(dlg_mod, "BrainV3FeedbackPopup", _CapturePopup)

    dialog = dlg_mod.BrainV3LearningSessionDialog.__new__(
        dlg_mod.BrainV3LearningSessionDialog
    )
    dialog._service = None
    dialog._contexts = {}
    dialog._contributions = dict(contribs)

    item = QListWidgetItem("cut")
    item.setData(Qt.ItemDataRole.UserRole, cut_id)
    dlg_mod.BrainV3LearningSessionDialog._open_feedback_for(dialog, item)

    assert "axis_contributions" in captured, (
        f"Popup-Payload ohne axis_contributions: {sorted(captured)}"
    )
    assert captured["axis_contributions"] == contribs[cut_id]


# ── (c) Dialog-Pfad landet im weighted-Credit ────────────────────────────
def test_dialog_path_feedback_is_weighted_not_uniform(
    isolated_appdata, db_session, tmp_path,
):
    project_root, entries = _seed_project(db_session, tmp_path)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_from_entries(
        project_root, entries, session_factory=_sf,
    ) is True

    contribs = load_learning_axis_contributions(project_root=project_root)
    assert contribs, "Dialog haette keine Achsen-Beitraege weiterzureichen"
    cut_id = next(iter(contribs))

    svc = BrainV3Service(project_root=project_root, session_factory=_sf)
    resp = svc.feedback(
        FeedbackRequest(cut_id=int(cut_id), rating="perfect"),
        axis_contributions=contribs[cut_id],
    )
    assert resp.credit_mode == "weighted"
    assert 0 < resp.n_axes_credited < 18
    assert resp.n_buckets_updated < 108


# ── (d) Bestandszeile ohne Achsen-Scores -> sauberer Uniform-Fallback ────
def test_legacy_confidence_only_row_falls_back_to_uniform(
    isolated_appdata, db_session, tmp_path,
):
    project_root, entries = _seed_project(db_session, tmp_path)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_from_entries(
        project_root, entries, session_factory=_sf,
    ) is True

    # Bestandsdaten simulieren: exakt der alte Platzhalter.
    with sqlite3.connect(state_db_path(project_root)) as conn:
        conn.execute(
            'UPDATE timeline_cuts SET brain_v3_scores_json = \'{"confidence": 0.5}\''
        )
        conn.commit()
        cut_id = conn.execute(
            "SELECT c.id FROM timeline_cuts c JOIN timelines t "
            "ON t.id = c.timeline_id WHERE t.is_current = 1"
        ).fetchone()[0]

    contribs = load_learning_axis_contributions(project_root=project_root)
    assert contribs == {}, "Alt-Zeile darf keine Achsen-Beitraege erfinden"

    svc = BrainV3Service(project_root=project_root, session_factory=_sf)
    resp = svc.feedback(
        FeedbackRequest(cut_id=int(cut_id), rating="perfect"),
        axis_contributions=contribs.get(int(cut_id)),
    )
    assert resp.credit_mode == "uniform"
    assert resp.n_axes_credited == 18
