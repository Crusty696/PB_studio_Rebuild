"""B-683: apply_auto_edit_segments — Retry-Backoff muss kurz UND ausserhalb des
_timeline_write_lock laufen.

Frueher lag der 5..20s-Backoff-``sleep`` INNERHALB `with _timeline_write_lock`
und lief synchron im GUI-Thread -> bis ~50s UI-Freeze + Blockade jedes anderen
Applies. busy_timeout=120s (nullpool_session) leistet das eigentliche Warten
bereits, der lange Backoff war redundant.
"""

import time

import pytest
from sqlalchemy.exc import OperationalError

import services.timeline_service as ts


def _locked_error():
    return OperationalError("DELETE FROM ...", {}, Exception("database is locked"))


@pytest.fixture(autouse=True)
def _stub_apply_deps(monkeypatch):
    monkeypatch.setattr(ts, "repair_timeline_integrity", lambda pid: None)
    monkeypatch.setattr(
        "services.timeline_snapshot_service.create_snapshot",
        lambda *a, **k: None,
    )


def test_backoff_is_short_and_outside_lock(monkeypatch):
    calls = {"n": 0}

    def _fake_apply(segments, project_id):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _locked_error()
        return 7

    monkeypatch.setattr(ts, "_do_apply_segments", _fake_apply)

    sleeps = []
    lock_free_during_sleep = []

    def _fake_sleep(secs):
        sleeps.append(secs)
        # B-683-Kern: waehrend der Wartezeit darf der Lock NICHT gehalten sein.
        lock_free_during_sleep.append(not ts._timeline_write_lock.locked())

    monkeypatch.setattr(time, "sleep", _fake_sleep)

    result = ts.apply_auto_edit_segments([], project_id=1, max_retries=5)

    assert result == 7
    assert calls["n"] == 3, "muss bis zum Erfolg wiederholen"
    # Zwei Fehlversuche -> zwei Backoffs, beide kurz (nicht 5/10s).
    assert sleeps == [0.5, 1.0]
    assert all(lock_free_during_sleep), (
        "Backoff-sleep lief mit gehaltenem _timeline_write_lock (B-683)"
    )


def test_persistent_lock_raises_after_retries(monkeypatch):
    def _always_locked(segments, project_id):
        raise _locked_error()

    monkeypatch.setattr(ts, "_do_apply_segments", _always_locked)
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    with pytest.raises(OperationalError, match="database is locked"):
        ts.apply_auto_edit_segments([], project_id=1, max_retries=3)


def test_non_lock_operationalerror_not_retried(monkeypatch):
    calls = {"n": 0}

    def _other_error(segments, project_id):
        calls["n"] += 1
        raise OperationalError("X", {}, Exception("no such table: foo"))

    monkeypatch.setattr(ts, "_do_apply_segments", _other_error)
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    with pytest.raises(OperationalError, match="no such table"):
        ts.apply_auto_edit_segments([], project_id=1, max_retries=5)
    assert calls["n"] == 1, "nicht-lock-Fehler darf NICHT wiederholt werden"
