"""B-628: das Retry-Budget muss die tatsaechliche Blockadezeit deckeln.

`_sync_anchors` laeuft im GUI-Thread. `_TOTAL_RETRY_BUDGET_SEC` (150 s) soll
garantieren, dass die App bei belegter DB nicht laenger einfriert. Der Deckel
griff urspruenglich nur an der falschen Stelle: geprueft wurde nur, ob VOR
einem neuen Versuch noch Budget uebrig ist — der begonnene Versuch lief danach
in den vollen `busy_timeout` von 120 s. Gemessen: Budget plus ein ganzer
zusaetzlicher busy_timeout, real rund 240 s statt 150 s.

Die bestehende Datei `test_b628_retry_budget_haelt.py` prueft das per
`inspect.getsource()` und Regex — sie sieht also nur, OB die Zeichenketten im
Quelltext stehen. Ein Refactor, der die Ableitung umbenennt, bricht sie
grundlos; ein Refactor, der sie kaputtmacht aber die Strings behaelt, kommt
durch. Diese Datei misst stattdessen das Verhalten an einer echten,
dauerhaft gesperrten SQLite-Datei.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from database.models import Base

# Skaliert: echte Werte waeren 120 s busy_timeout und 150 s Budget — das
# liesse den Test minutenlang laufen. Das Verhaeltnis ist das gleiche:
# ein einzelner busy_timeout ist deutlich groesser als das Restbudget.
_BUSY_TIMEOUT_MS = 10_000
_BUDGET_SEC = 3.0
# Ohne den Fix waere die Dauer rund _BUDGET_SEC + _BUSY_TIMEOUT_MS/1000 = 13 s.
_TOLERANZ_SEC = 3.0


@contextmanager
def _dauerblocker(db_path: str):
    """Haelt eine exklusive Schreibsperre, bis der Block verlassen wird."""
    freigeben = threading.Event()
    haelt = threading.Event()

    def _halten() -> None:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN EXCLUSIVE")
            haelt.set()
            freigeben.wait(timeout=60)
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()

    t = threading.Thread(target=_halten, daemon=True)
    t.start()
    assert haelt.wait(timeout=10), "Blocker-Thread bekam die Sperre nicht"
    try:
        yield
    finally:
        freigeben.set()
        t.join(timeout=10)


def _engine_mit_busy_timeout(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        cur.close()

    return engine


@pytest.mark.timeout(60) if hasattr(pytest.mark, "timeout") else (lambda f: f)
def test_b628_blockadezeit_bleibt_im_budget(tmp_path, monkeypatch):
    """Der eigentliche Vertrag: die Wall-Clock-Dauer sprengt das Budget nicht.

    Ohne die Ableitung des `busy_timeout` aus dem Restbudget laeuft der letzte
    begonnene Versuch in den vollen Vorgabewert — die Dauer waere dann rund
    Budget + busy_timeout statt nur Budget.
    """
    from services import anchor_sync_service as ass

    db_path = str(tmp_path / "locked.db")
    setup_engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    Base.metadata.create_all(setup_engine)
    with setup_engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    setup_engine.dispose()

    engine = _engine_mit_busy_timeout(db_path)

    @contextmanager
    def _fake_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(ass, "nullpool_session", _fake_session)
    monkeypatch.setattr(ass, "_TOTAL_RETRY_BUDGET_SEC", _BUDGET_SEC)

    with _dauerblocker(db_path):
        start = time.monotonic()
        with pytest.raises(ass.AnchorSyncLockedError):
            ass.sync_dialog_anchors(
                audio_track_id=1,
                anchors=[{"audio_time": 1.0, "scene_id": 1}],
            )
        dauer = time.monotonic() - start

    assert dauer < _BUDGET_SEC + _TOLERANZ_SEC, (
        f"B-628: Blockade dauerte {dauer:.2f}s bei einem Budget von "
        f"{_BUDGET_SEC:.0f}s. Ein begonnener Versuch laeuft offenbar wieder in "
        f"den vollen busy_timeout ({_BUSY_TIMEOUT_MS/1000:.0f}s), statt ihn aus "
        f"dem Restbudget abzuleiten."
    )


def test_b628_erfolgreicher_lauf_wird_nicht_ausgebremst(tmp_path, monkeypatch):
    """Gegenprobe: ohne Sperre darf der Deckel nichts kosten.

    Sonst waere nicht unterscheidbar, ob der Test die Budgetlogik misst oder
    nur, dass die Funktion irgendwann aufgibt.
    """
    from services import anchor_sync_service as ass
    from database.models import AudioTrack, Project, Scene, VideoClip

    db_path = str(tmp_path / "frei.db")
    engine = _engine_mit_busy_timeout(db_path)
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Project(id=1, name="p", path=str(tmp_path), resolution="1920x1080", fps=30.0))
        s.add(AudioTrack(id=1, project_id=1, file_path="a.wav"))
        s.add(VideoClip(id=1, project_id=1, file_path="v.mp4"))
        s.add(Scene(id=1, video_clip_id=1, scene_index=0, start_time=2.5, end_time=5.0))
        s.commit()

    @contextmanager
    def _fake_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(ass, "nullpool_session", _fake_session)
    monkeypatch.setattr(ass, "_TOTAL_RETRY_BUDGET_SEC", _BUDGET_SEC)

    start = time.monotonic()
    persisted = ass.sync_dialog_anchors(
        audio_track_id=1,
        anchors=[{"audio_time": 1.0, "scene_id": 1}],
    )
    dauer = time.monotonic() - start

    assert persisted == 1
    assert dauer < 2.0, f"ungesperrter Lauf brauchte {dauer:.2f}s — da wartet etwas"
