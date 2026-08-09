"""B-784 — Der Brain-Lernkreis braucht einen Produktions-Aufrufer.

Befund im Bugfile: ``sync_current_timeline_from_entries`` ist die einzige
Funktion, die ``timeline_cuts`` in ``brain_v3/state.db`` schreibt, hat aber
ausser Tests keinen Aufrufer. Damit laufen B-732/B-733/B-781 live ins Leere —
``BrainV3Service.learning_session`` faellt immer auf den Weight-Bucket-Sampler
zurueck.

Vertraege:
  (a) Nach dem Auto-Edit-Apply existieren echte ``timeline_cuts``:
      a1 = der Service-Einstieg ``sync_current_timeline_after_apply`` baut sie
           aus den echten ``TimelineEntry``-Zeilen,
      a2 = der Apply-Pfad der UI ruft ihn tatsaechlich auf (Spy) und blockiert
           dabei den GUI-Thread nicht.
  (b) Ein zweiter Run mit IDENTISCHER Geometrie aktualisiert trotzdem die
      Achsen-Scores (alte Change-Detection verglich nur die Geometrie).
  (c) Wirklich unveraenderter Zustand schreibt nicht sinnlos.
  (d) Ein Sync-Fehler laesst den Apply NICHT scheitern.

CPU-only, Qt offscreen, kein ``.exec()``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from database import AudioTrack, Project, Scene, TimelineEntry, VideoClip
from services.brain.timeline_state import state_db_path

REAL_AXIS_SCORES = {
    "energy_weight": 0.8,
    "role_match_weight": 0.2,
    "beat_weight": 0.0,
}

CUT_START_S = 16.0
CUT_END_S = 20.0


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def _sql(statement: str):
    from sqlalchemy import text as _text

    return _text(statement)


def _create_mem_tables(session) -> None:
    """``mem_pacing_run``/``mem_decision`` existieren nur als Alembic-Revision.

    Die In-Memory-Engine der Tests baut nur ORM-Tabellen; identisches Vorgehen
    wie ``tests/test_services/test_b781_axis_contributions_dialog.py``.
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


def _seed_project(db_session, tmp_path: Path):
    """Projekt + Audio + Video + Scene + ECHTE TimelineEntry-Zeilen.

    Die TimelineEntry-Zeilen sind das, was ``apply_auto_edit_segments`` nach
    einem Auto-Edit in der Haupt-DB hinterlaesst — genau der Zustand, aus dem
    der Sync den Brain-V3-Lernzustand ableiten muss.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_file = tmp_path / "mix.mp3"
    video_file = tmp_path / "clip.mp4"
    audio_file.write_bytes(b"id3")
    video_file.write_bytes(b"mp4")

    project = Project(
        name="B784", path=str(project_root), resolution="1920x1080", fps=30,
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

    db_session.add_all([
        TimelineEntry(
            project_id=project.id, track="audio", media_id=audio.id,
            start_time=0.0, end_time=120.0, source_start=0.0, source_end=120.0,
        ),
        TimelineEntry(
            project_id=project.id, track="video", media_id=video.id,
            start_time=CUT_START_S, end_time=CUT_END_S,
            source_start=0.0, source_end=4.0,
        ),
    ])
    db_session.commit()

    _create_mem_tables(db_session)
    return project, project_root, audio, video, scene


def _insert_decision(db_session, audio_id: int, scene_id: int, scores: dict) -> None:
    db_session.execute(
        _sql(
            "INSERT INTO mem_pacing_run(audio_track_id, started_at) "
            "VALUES (:aid, '2026-08-09T10:00:00')"
        ),
        {"aid": int(audio_id)},
    )
    run_id = db_session.execute(
        _sql("SELECT id FROM mem_pacing_run ORDER BY id DESC LIMIT 1")
    ).scalar()
    db_session.execute(
        _sql(
            "INSERT INTO mem_decision("
            " run_id, sequence_idx, at_timestamp_sec, scene_id, agent_rationale"
            ") VALUES (:rid, 0, :ts, :sid, :rat)"
        ),
        {
            "rid": int(run_id),
            "ts": CUT_START_S,
            "sid": int(scene_id),
            "rat": json.dumps({"brain_v3_scores": scores}),
        },
    )
    db_session.commit()


def _read_cuts(project_root: Path) -> list[tuple]:
    with sqlite3.connect(state_db_path(project_root)) as conn:
        return conn.execute(
            "SELECT c.id, c.brain_v3_scores_json FROM timeline_cuts c "
            "JOIN timelines t ON t.id = c.timeline_id WHERE t.is_current = 1 "
            "ORDER BY c.position_idx ASC, c.id ASC"
        ).fetchall()


def _count_timelines(project_root: Path) -> int:
    with sqlite3.connect(state_db_path(project_root)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM timelines").fetchone()[0])


# ── (a1) Service-Einstieg baut die Cuts aus den echten Timeline-Zeilen ───
def test_sync_after_apply_creates_timeline_cuts_from_db(
    isolated_appdata, db_session, tmp_path,
):
    from services.brain.timeline_state import sync_current_timeline_after_apply

    project, project_root, audio, video, scene = _seed_project(db_session, tmp_path)
    _insert_decision(db_session, audio.id, scene.id, REAL_AXIS_SCORES)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_after_apply(
        project_id=project.id, project_root=project_root, session_factory=_sf,
    ) is True

    cuts = _read_cuts(project_root)
    assert len(cuts) == 1, f"Kein timeline_cut aus den TimelineEntry-Zeilen: {cuts!r}"
    assert json.loads(cuts[0][1]).get("brain_v3_scores") == REAL_AXIS_SCORES


# ── (a2) Der UI-Apply-Pfad ruft den Sync wirklich auf, off-thread ────────
def test_auto_edit_apply_path_triggers_learning_sync(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    import services.brain.timeline_state as ts_state
    import ui.controllers.edit_workspace as ew_mod
    import ui.undo_commands as undo_mod

    calls: list[dict] = []

    def _spy(project_id=None, project_root=None, session_factory=None):
        calls.append({
            "project_id": project_id,
            "thread": threading.current_thread().ident,
        })
        return True

    monkeypatch.setattr(ts_state, "sync_current_timeline_after_apply", _spy)
    monkeypatch.setattr(ew_mod, "get_active_project_id", lambda: 4711)

    class _FakeCmd:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(undo_mod, "ApplyAutoEditCommand", _FakeCmd)

    ctrl = ew_mod.EditWorkspaceController.__new__(ew_mod.EditWorkspaceController)
    ctrl.window = MagicMock()
    # Die beiden Deferred-Refreshes am Methodenende gehoeren nicht zu diesem
    # Vertrag und brauchen eine echte MainWindow-Instanz.
    ctrl._defer_cut_list_refresh = lambda *_a, **_k: None
    ctrl._defer_schnitt_workspace_refresh = lambda *_a, **_k: None

    segments = [{"media_id": 3, "start": 0.0, "end": 5.0}]
    ctrl._on_auto_edit_finished(segments, [], "task-1", audio_id_override=1)

    thread = getattr(ctrl, "_brain_learning_sync_thread", None)
    assert thread is not None, (
        "Apply-Pfad startet keinen Brain-V3-Lern-Sync (B-784)"
    )
    thread.join(timeout=10)
    assert calls, "sync_current_timeline_after_apply wurde nie aufgerufen"
    assert calls[0]["project_id"] == 4711
    assert calls[0]["thread"] != threading.current_thread().ident, (
        "Sync lief im GUI-Thread — Apply-Pfad laeuft laut "
        "worker_dispatcher (QueuedConnection) im GUI-Thread"
    )


def test_second_apply_while_sync_runs_does_not_start_a_second_thread(monkeypatch):
    """Zwei Auto-Edits kurz hintereinander duerfen nicht parallel auf
    dieselbe state.db schreiben — SQLite quittiert das mit
    "database is locked" und der zweite Lauf ginge verloren."""
    pytest.importorskip("PySide6")
    import ui.controllers.edit_workspace as ew_mod

    ctrl = ew_mod.EditWorkspaceController.__new__(ew_mod.EditWorkspaceController)

    class _AliveThread:
        def is_alive(self):
            return True

    ctrl._brain_learning_sync_thread = _AliveThread()
    assert ctrl._start_brain_learning_sync(4711) is None
    # Referenz unveraendert: der laufende Thread wurde nicht ersetzt.
    assert isinstance(ctrl._brain_learning_sync_thread, _AliveThread)


def test_finished_sync_thread_allows_next_start(monkeypatch):
    """Ein abgeschlossener Lauf darf den naechsten nicht blockieren."""
    pytest.importorskip("PySide6")
    import services.brain.timeline_state as ts_state
    import ui.controllers.edit_workspace as ew_mod

    monkeypatch.setattr(
        ts_state, "sync_current_timeline_after_apply",
        lambda **_kw: True,
    )
    ctrl = ew_mod.EditWorkspaceController.__new__(ew_mod.EditWorkspaceController)

    class _DeadThread:
        def is_alive(self):
            return False

    ctrl._brain_learning_sync_thread = _DeadThread()
    thread = ctrl._start_brain_learning_sync(4711)
    assert thread is not None
    thread.join(timeout=10)


# ── (b) gleiche Geometrie, neue Entscheidungen -> Scores werden aktuell ──
def test_second_run_same_geometry_still_refreshes_axis_scores(
    isolated_appdata, db_session, tmp_path,
):
    from services.brain.timeline_state import sync_current_timeline_after_apply

    project, project_root, audio, video, scene = _seed_project(db_session, tmp_path)

    @contextmanager
    def _sf():
        yield db_session

    # 1. Sync ohne Pacing-Run -> Platzhalter
    assert sync_current_timeline_after_apply(
        project_id=project.id, project_root=project_root, session_factory=_sf,
    ) is True
    first = _read_cuts(project_root)
    assert json.loads(first[0][1]).get("brain_v3_scores") is None

    # 2. Pacing-Run laeuft, Geometrie bleibt IDENTISCH
    _insert_decision(db_session, audio.id, scene.id, REAL_AXIS_SCORES)

    assert sync_current_timeline_after_apply(
        project_id=project.id, project_root=project_root, session_factory=_sf,
    ) is True, "Sync meldet 'unveraendert', obwohl neue mem_decision-Zeilen da sind"

    second = _read_cuts(project_root)
    assert json.loads(second[0][1]).get("brain_v3_scores") == REAL_AXIS_SCORES
    assert json.loads(second[0][1]).get("confidence") == 0.5


# ── (c) wirklich unveraendert -> kein sinnloser Schreibvorgang ───────────
def test_unchanged_state_does_not_rewrite(
    isolated_appdata, db_session, tmp_path,
):
    from services.brain.timeline_state import sync_current_timeline_after_apply

    project, project_root, audio, video, scene = _seed_project(db_session, tmp_path)
    _insert_decision(db_session, audio.id, scene.id, REAL_AXIS_SCORES)

    @contextmanager
    def _sf():
        yield db_session

    assert sync_current_timeline_after_apply(
        project_id=project.id, project_root=project_root, session_factory=_sf,
    ) is True
    before = _read_cuts(project_root)
    timelines_before = _count_timelines(project_root)

    assert sync_current_timeline_after_apply(
        project_id=project.id, project_root=project_root, session_factory=_sf,
    ) is False, "Unveraenderter Zustand darf nicht erneut geschrieben werden"

    assert _read_cuts(project_root) == before
    assert _count_timelines(project_root) == timelines_before


# ── (d) Sync-Fehler bricht den Apply nicht ───────────────────────────────
def test_sync_failure_is_swallowed(isolated_appdata, tmp_path):
    from services.brain.timeline_state import sync_current_timeline_after_apply

    @contextmanager
    def _broken_sf():
        raise sqlite3.OperationalError("no such table: timeline_entries")
        yield  # pragma: no cover

    assert sync_current_timeline_after_apply(
        project_id=1, project_root=tmp_path / "nope", session_factory=_broken_sf,
    ) is False


def test_sync_failure_does_not_break_auto_edit_apply(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    import ui.controllers.edit_workspace as ew_mod
    import ui.undo_commands as undo_mod

    pushed: list = []

    class _FakeCmd:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(undo_mod, "ApplyAutoEditCommand", _FakeCmd)
    monkeypatch.setattr(ew_mod, "get_active_project_id", lambda: 4711)

    def _boom(*_a, **_k):
        raise RuntimeError("Thread-Start kaputt")

    monkeypatch.setattr(ew_mod.threading, "Thread", _boom)

    ctrl = ew_mod.EditWorkspaceController.__new__(ew_mod.EditWorkspaceController)
    ctrl.window = MagicMock()
    ctrl.window.timeline_view.undo_stack.push = pushed.append
    ctrl._defer_cut_list_refresh = lambda *_a, **_k: None
    ctrl._defer_schnitt_workspace_refresh = lambda *_a, **_k: None

    ctrl._on_auto_edit_finished(
        [{"media_id": 3, "start": 0.0, "end": 5.0}], [], "task-2", audio_id_override=1,
    )

    assert len(pushed) == 1, "Apply wurde durch den Sync-Fehler verhindert"
