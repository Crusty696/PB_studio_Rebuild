"""B-779 — Retry/Backoff um den Dialog-Anker-Write.

B-628 setzte ``busy_timeout=120s``. Das haelt realistischer Import-Last stand,
ist aber kein Absolutschutz: unter Dauer-Saettigung laeuft der Timeout ab und
derselbe ``OperationalError: database is locked`` kehrt zurueck (live belegt,
reproduzierbar nach ~131 s).

Vertraege hier:
(a) transienter Lock -> Sync gelingt nach Retry, Anker landen in der DB,
(b) Dauer-Lock -> sprechender ``AnchorSyncLockedError`` statt rohem
    ``OperationalError``,
(c) ohne Contention kein zusaetzlicher Retry/Delay,
(d) Nachtrag 2026-08-09: der einzige Callsite
    (ui/controllers/edit_workspace.py::_sync_anchors) laeuft im GUI-Thread.
    ``_TOTAL_RETRY_BUDGET_SEC`` deckelt daher die Gesamtdauer aller Versuche
    — ohne Deckel haette der Retry das Worst-Case-Freeze-Budget von einem
    busy_timeout (120 s) auf drei verdreifacht.
"""

import importlib
import time
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import database
from database import AudioVideoAnchor


@pytest.fixture
def _patched_service(test_engine, monkeypatch):
    """Leitet nullpool_session() im Service auf die Test-Engine um."""
    mod = importlib.import_module("services.anchor_sync_service")

    @contextmanager
    def _test_nullpool():
        with Session(test_engine) as s:
            yield s

    monkeypatch.setattr(mod, "nullpool_session", _test_nullpool)
    return mod


@pytest.fixture
def _no_sleep(monkeypatch):
    """Backoff-Sleep neutralisieren und protokollieren.

    Patcht ``time.sleep`` am Modul-Objekt — der Service importiert
    ``time as _time``, also dieselbe Referenz.

    Der Patch ist damit aber prozessweit: Hintergrund-Threads aus
    frueher gelaufenen Tests (Polling-Schleifen, Qt-Timer) schlagen
    sonst mit auf und blaehen die Liste auf. Im Gesamtlauf standen so
    1.519.712 statt 2 Eintraege — der Test war nur isoliert gruen.
    Deshalb ausschliesslich Sleeps des Testthreads zaehlen; der
    Retry-Loop von ``sync_dialog_anchors`` laeuft synchron in genau
    diesem Thread.
    """
    import threading

    waits: list[float] = []
    _test_thread_id = threading.get_ident()

    def _fake_sleep(seconds):
        if threading.get_ident() == _test_thread_id:
            waits.append(seconds)

    monkeypatch.setattr(time, "sleep", _fake_sleep)
    return waits


def _locked_error() -> OperationalError:
    """Baut denselben Fehler, den SQLite unter Lock-Contention liefert."""
    return OperationalError(
        "DELETE FROM audio_video_anchors WHERE audio_video_anchors.audio_track_id = ?",
        (998, "dialog"),
        Exception("database is locked"),
    )


def _flaky_session(mod, real_ctx, fail_times: int, counter: dict):
    """nullpool_session-Ersatz, der die ersten ``fail_times`` Versuche sperrt."""

    @contextmanager
    def _ctx():
        counter["n"] += 1
        if counter["n"] <= fail_times:
            raise _locked_error()
        with real_ctx() as s:
            yield s

    return _ctx


# ---------------------------------------------------------------------------
# (d) GUI-Thread-Schutz: Gesamtbudget deckelt die Blockadezeit
# ---------------------------------------------------------------------------

def test_exhausted_time_budget_stops_retrying(
    _patched_service, _no_sleep, monkeypatch, audio_track
):
    """Ein Versuch, der das Budget aufbraucht, darf keinen Retry ausloesen.

    Sonst blockiert der GUI-Thread im Worst Case 3x busy_timeout statt 1x.
    """
    mod = _patched_service
    counter = {"n": 0}

    @contextmanager
    def _slow_locked():
        counter["n"] += 1
        # Simuliert einen Versuch, der das gesamte Budget verbraucht hat.
        monkeypatch.setattr(
            mod._time, "monotonic",
            lambda: _base + mod._TOTAL_RETRY_BUDGET_SEC + 1.0,
        )
        raise _locked_error()
        yield  # pragma: no cover

    _base = mod._time.monotonic()
    monkeypatch.setattr(mod, "nullpool_session", _slow_locked)

    with pytest.raises(mod.AnchorSyncLockedError):
        mod.sync_dialog_anchors(audio_track.id, [{"audio_time": 1.0, "scene_id": "1"}])

    assert counter["n"] == 1, (
        "Budget war nach dem ersten Versuch aufgebraucht — kein Retry erlaubt"
    )
    assert _no_sleep == [], "kein Backoff-Sleep bei erschoepftem Budget"


def test_budget_constant_is_near_single_busy_timeout():
    """Das Budget darf das Freeze-Fenster nicht vervielfachen."""
    mod = importlib.import_module("services.anchor_sync_service")
    # busy_timeout ist 120s (database/session.py). Knapp darueber ist ok,
    # ein Vielfaches waere der Freeze, den der Deckel verhindern soll.
    assert 120.0 <= mod._TOTAL_RETRY_BUDGET_SEC <= 200.0


# ---------------------------------------------------------------------------
# (a) transienter Lock -> Erfolg
# ---------------------------------------------------------------------------

def test_transient_lock_retries_and_persists(
    _patched_service, _no_sleep, monkeypatch, db_session, audio_track, video_clip
):
    """Erste 2 Versuche 'database is locked', 3. gelingt -> Anker in der DB."""
    mod = _patched_service
    scene = database.Scene(
        video_clip_id=video_clip.id, start_time=1.5, end_time=3.0, label="S1"
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(scene)

    counter = {"n": 0}
    monkeypatch.setattr(
        mod, "nullpool_session",
        _flaky_session(mod, mod.nullpool_session, fail_times=2, counter=counter),
    )

    count = mod.sync_dialog_anchors(
        audio_track.id, [{"audio_time": 10.0, "scene_id": str(scene.id)}]
    )

    assert count == 1
    assert counter["n"] == 3, "muss bis zum Erfolg retrien"
    assert len(_no_sleep) == 2, "zwei Backoff-Pausen vor dem erfolgreichen Versuch"

    row = db_session.query(AudioVideoAnchor).filter(
        AudioVideoAnchor.audio_track_id == audio_track.id
    ).one()
    assert row.video_clip_id == video_clip.id
    assert row.audio_time == pytest.approx(10.0)
    assert row.anchor_type == "dialog"


def test_backoff_is_exponential_with_jitter(
    _patched_service, _no_sleep, monkeypatch, audio_track
):
    """B-073-Pattern: base 2**attempt * jitter(0.5-1.5) — wie onset_rhythm_service.

    B-827: fester Seed. Die letzte Assertion ("steigende Tendenz") ist keine
    Zusage, die der Code pro Einzellauf gibt — bei `j0=1.5` und `j1=0.5` gilt
    `2*0.5 > 1*1.5*0.9` nicht. Gemessen ueber 20000 Ziehungen faellt sie in
    3.24 % der Faelle. Ohne Seed war der Test damit reihenfolgeabhaengig rot,
    ohne dass sich am Produktcode etwas geaendert haette. Die Ranges darueber
    sind die eigentliche Zusage und gelten immer.
    """
    import random as _rnd
    _rnd.seed(779)

    mod = _patched_service
    counter = {"n": 0}
    monkeypatch.setattr(
        mod, "nullpool_session",
        _flaky_session(mod, mod.nullpool_session, fail_times=2, counter=counter),
    )

    mod.sync_dialog_anchors(audio_track.id, [])

    assert len(_no_sleep) == 2
    assert 0.5 <= _no_sleep[0] <= 1.5      # 2**0 * jitter
    assert 1.0 <= _no_sleep[1] <= 3.0      # 2**1 * jitter
    assert _no_sleep[1] > _no_sleep[0] * 0.9  # steigende Tendenz


# ---------------------------------------------------------------------------
# (b) Dauer-Lock -> sprechender Fehler
# ---------------------------------------------------------------------------

def test_permanent_lock_raises_speaking_error(
    _patched_service, _no_sleep, monkeypatch, audio_track
):
    """Nach erschoepften Retries: AnchorSyncLockedError, kein roher OperationalError."""
    mod = _patched_service
    counter = {"n": 0}
    monkeypatch.setattr(
        mod, "nullpool_session",
        _flaky_session(mod, mod.nullpool_session, fail_times=99, counter=counter),
    )

    locked_error = getattr(mod, "AnchorSyncLockedError", None)
    assert locked_error is not None, (
        "Service muss einen sprechenden Lock-Fehlertyp exportieren, "
        "statt den rohen OperationalError durchzureichen"
    )

    with pytest.raises(Exception) as exc:  # noqa: PT011 - Typ ist genau der Vertrag
        mod.sync_dialog_anchors(audio_track.id, [{"audio_time": 1.0, "scene_id": "1"}])

    assert isinstance(exc.value, locked_error), type(exc.value)
    assert not isinstance(exc.value, OperationalError)
    msg = str(exc.value)
    assert "Lock" in msg or "lock" in msg, msg
    assert str(audio_track.id) in msg, msg
    assert isinstance(exc.value.__cause__, OperationalError), "Ursache bleibt verkettet"
    # B-073-Budget: 3 Versuche, 2 Backoff-Pausen (wie onset_rhythm_service).
    assert counter["n"] == 3, counter["n"]
    assert len(_no_sleep) == 2, _no_sleep


def test_non_lock_error_is_not_retried(_patched_service, _no_sleep, monkeypatch, audio_track):
    """Andere Fehler duerfen weder retried noch in AnchorSyncLockedError verpackt werden."""
    mod = _patched_service
    counter = {"n": 0}

    @contextmanager
    def _boom():
        counter["n"] += 1
        raise ValueError("kaputte Spalte")
        yield  # pragma: no cover

    monkeypatch.setattr(mod, "nullpool_session", _boom)

    with pytest.raises(ValueError):
        mod.sync_dialog_anchors(audio_track.id, [])

    assert counter["n"] == 1
    assert _no_sleep == []


# ---------------------------------------------------------------------------
# (c) ohne Contention kein Extra-Delay
# ---------------------------------------------------------------------------

def test_no_contention_no_extra_delay(
    _patched_service, _no_sleep, monkeypatch, db_session, audio_track, video_clip
):
    """Happy Path: genau eine Session, kein sleep, Bestandsverhalten unveraendert."""
    mod = _patched_service
    real_ctx = mod.nullpool_session
    counter = {"n": 0}

    @contextmanager
    def _spy():
        counter["n"] += 1
        with real_ctx() as s:
            yield s

    monkeypatch.setattr(mod, "nullpool_session", _spy)

    count = mod.sync_dialog_anchors(
        audio_track.id, [{"audio_time": 5.0, "scene_id": f"clip_{video_clip.id}"}]
    )

    assert count == 1
    assert counter["n"] == 1, "kein zusaetzlicher Session-Aufbau ohne Contention"
    assert _no_sleep == [], "kein Backoff-Delay im Normalfall"
