"""B-294: SCHNITT Empty-State Preset-Klick muss Pipeline starten, nicht silent return.
Adapter ruft _ensure_combos_filled_from_project (via _guard_combos_or_notify)."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from ui.controllers.edit_workspace import EditWorkspaceController


# ---------------------------------------------------------------------------
# Source-level guards (Phase C original — adapter wiring + helper presence).
# ---------------------------------------------------------------------------


def test_b294_ensure_combos_filled_helper_exists():
    assert hasattr(EditWorkspaceController, "_ensure_combos_filled_from_project")


def test_b294_guard_helper_exists():
    """R-23 M-1: extrahierter DRY-Helper fuer Adapter-Slots."""
    assert hasattr(EditWorkspaceController, "_guard_combos_or_notify")


def test_b294_auto_edit_adapter_calls_ensure_combos():
    src = inspect.getsource(EditWorkspaceController._on_schnitt_auto_edit_request)
    # After M-1 refactor: adapter calls _guard_combos_or_notify which itself
    # calls _ensure_combos_filled_from_project. Either reference is OK.
    assert "_guard_combos_or_notify" in src or "_ensure_combos_filled_from_project" in src, (
        "B-294: _on_schnitt_auto_edit_request ruft Auto-Fill-Helper nicht."
    )


def test_b294_regenerate_adapter_calls_ensure_combos():
    src = inspect.getsource(EditWorkspaceController._on_schnitt_regenerate_request)
    assert "_guard_combos_or_notify" in src or "_ensure_combos_filled_from_project" in src, (
        "B-294: _on_schnitt_regenerate_request ruft Auto-Fill-Helper nicht."
    )


def test_b294_ensure_combos_signature():
    sig = inspect.signature(EditWorkspaceController._ensure_combos_filled_from_project)
    # Method should return bool, no extra args besides self
    assert sig.return_annotation in (bool, "bool"), (
        f"B-294: _ensure_combos_filled_from_project sollte -> bool zurueckgeben (sig={sig})"
    )


# ---------------------------------------------------------------------------
# R-23 I-2: Behavioral tests for _ensure_combos_filled_from_project.
#
# Strategy: MagicMock-based with monkeypatch on get_active_project_id and a
# stubbed query-chain. Avoids the EngineProxy/DBSession import-time binding
# pitfall (the helper does `from database import engine, ...` inside its
# body, so test_engine's `database.engine` patch IS picked up — but
# get_active_project_id reads `database.session.engine` which is not).
#
# Per spec: at least ONE behavioral test required. We deliver TWO via mocks
# (empty-DB path returns False; populated-DB path returns True with combos
# set). DBSession is stubbed via a small context-manager so the helper's
# `with DBSession(engine) as s: s.query(...).filter_by(...).first()` chain
# is exercised end-to-end including the post-setCurrentIndex re-check.
# ---------------------------------------------------------------------------


class _FakeQuery:
    """Minimal SQLAlchemy-style query chain returning a fixed .first() result."""
    def __init__(self, result):
        self._result = result

    def filter_by(self, **_kw):
        return self

    def filter(self, *_a, **_kw):
        return self

    def order_by(self, *_a, **_kw):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """Context-manager-capable fake session with model-keyed first() results."""
    def __init__(self, results_by_model):
        self._results = results_by_model

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def query(self, model):
        return _FakeQuery(self._results.get(model))


def _make_controller(audio_id=None, video_id=None):
    """Build a bare EditWorkspaceController with mocked combos.

    State dict captures setCurrentIndex calls so post-set currentData()
    reflects the helper's writes (real Qt combo behaviour).
    """
    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    ctrl.window = MagicMock()
    state = {"audio": audio_id, "video": video_id}

    def audio_curr():
        return state["audio"]

    def video_curr():
        return state["video"]

    ctrl.window.audio_combo.currentData = audio_curr
    ctrl.window.video_combo.currentData = video_curr
    ctrl.window.audio_combo.findData = lambda _id: 0
    ctrl.window.video_combo.findData = lambda _id: 0
    return ctrl, state


def test_b294_ensure_combos_fills_from_db(monkeypatch):
    """Behavioral: helper populates empty combos when project has audio+video."""
    import ui.controllers.edit_workspace as ew_mod  # noqa: F401 — imported for side-effect of module presence
    import database

    ctrl, state = _make_controller(audio_id=None, video_id=None)

    # setCurrentIndex mutates state so post-write currentData() returns the
    # new id — same observable contract as a real QComboBox.
    audio_row = MagicMock()
    audio_row.id = 42
    video_row = MagicMock()
    video_row.id = 99

    def audio_set(_idx):
        state["audio"] = audio_row.id

    def video_set(_idx):
        state["video"] = video_row.id

    ctrl.window.audio_combo.setCurrentIndex = audio_set
    ctrl.window.video_combo.setCurrentIndex = video_set

    # Patch active project lookup.
    monkeypatch.setattr(database, "get_active_project_id", lambda: 1)

    # Patch DBSession to return our fake session with seeded results.
    # Note: helper does `from sqlalchemy.orm import Session as DBSession`
    # *inside* the function body, so we patch the source module attribute.
    import sqlalchemy.orm as _saorm
    monkeypatch.setattr(
        _saorm,
        "Session",
        lambda _engine: _FakeSession({
            database.AudioTrack: audio_row,
            database.VideoClip: video_row,
        }),
    )

    result = ctrl._ensure_combos_filled_from_project()
    assert result is True
    assert state["audio"] == 42
    assert state["video"] == 99


def test_b294_ensure_combos_empty_db_returns_false(monkeypatch):
    """Behavioral: helper returns False when project has no audio/video rows."""
    import database

    ctrl, state = _make_controller(audio_id=None, video_id=None)
    # setCurrentIndex no-op — combos stay empty
    ctrl.window.audio_combo.setCurrentIndex = lambda _idx: None
    ctrl.window.video_combo.setCurrentIndex = lambda _idx: None

    monkeypatch.setattr(database, "get_active_project_id", lambda: 1)

    import sqlalchemy.orm as _saorm
    monkeypatch.setattr(
        _saorm,
        "Session",
        lambda _engine: _FakeSession({
            database.AudioTrack: None,
            database.VideoClip: None,
        }),
    )

    result = ctrl._ensure_combos_filled_from_project()
    assert result is False
    assert state["audio"] is None
    assert state["video"] is None


def test_b294_ensure_combos_no_active_project_returns_false(monkeypatch):
    """Behavioral: helper returns False when no active project (DB import-pattern safe)."""
    import database
    monkeypatch.setattr(database, "get_active_project_id", lambda: None)

    ctrl, _state = _make_controller(audio_id=None, video_id=None)
    result = ctrl._ensure_combos_filled_from_project()
    assert result is False


# ---------------------------------------------------------------------------
# R-23 I-3: AttributeError must escalate (Programmierfehler), not be swallowed.
# ---------------------------------------------------------------------------


def test_b294_attribute_error_escalates(monkeypatch):
    """I-3: Combo-Widget fehlt -> AttributeError MUSS hochkommen, nicht False."""
    import database
    monkeypatch.setattr(database, "get_active_project_id", lambda: 1)

    ctrl = EditWorkspaceController.__new__(EditWorkspaceController)
    # window without audio_combo -> AttributeError on first access in the try.
    class _Win:
        pass
    ctrl.window = _Win()  # no audio_combo attribute

    with pytest.raises(AttributeError):
        ctrl._ensure_combos_filled_from_project()
