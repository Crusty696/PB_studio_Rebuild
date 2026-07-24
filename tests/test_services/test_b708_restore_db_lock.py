"""B-708: Snapshot-Restore scheiterte an "database is locked", weil er als
einziger timeline_entries-Writer die Anti-Lock-Haertung (Retry-auf-locked +
_timeline_write_lock + nullpool_session) umging, die apply_auto_edit_segments
laengst hat.

Deterministischer Concurrency-Repro: ein zweiter Thread haelt per BEGIN IMMEDIATE
kurz den Write-Lock auf der (echten File-)DB; parallel laeuft restore_snapshot.
- Alt (ohne Retry): sofortiges "database is locked" -> Exception (RED).
- Neu (Retry-Schleife): wartet/retryt bis der Writer freigibt -> schreibt
  erfolgreich (GREEN).
"""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import database
from database.models import Project, TimelineEntry


@contextmanager
def _file_engine(tmp_path):
    db = tmp_path / "b708.db"
    eng = create_engine(
        f"sqlite:///{db.as_posix()}",
        # timeout=0: der Lock soll SOFORT als "database is locked" schlagen
        # (sqlite3-Default waere 5s und wuerde den kurzen Halter maskieren).
        # Damit ist die Retry-Schleife das messbar Behebende, nicht ein langer
        # busy_timeout — genau die Haertung, die dem Alt-Restore fehlte.
        connect_args={"check_same_thread": False, "timeout": 0},
    )
    database.Base.metadata.create_all(eng)
    with eng.connect() as c:
        c.exec_driver_sql("PRAGMA journal_mode=WAL")
    try:
        yield eng, db
    finally:
        eng.dispose()


def _hold_write_lock(db_path, started, release_after):
    """Zweiter Writer: BEGIN IMMEDIATE + Write, Transaktion offen halten."""
    conn = sqlite3.connect(str(db_path), timeout=0.1)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO timeline_entries (project_id, track, media_id, "
            "start_time, end_time, lane) VALUES (99, 'video', 1, 0.0, 1.0, 0)"
        )
        started.set()
        time.sleep(release_after)
        conn.rollback()  # Lock freigeben
    finally:
        conn.close()


def test_restore_succeeds_under_concurrent_writer(tmp_path, monkeypatch):
    with _file_engine(tmp_path) as (eng, db):
        import services.timeline_snapshot_service as tss
        import services.timeline_state as tstate

        # restore-Read/backup laufen ueber tss.engine; der Write ueber
        # database.nullpool_session (lazy importiert in restore_snapshot).
        monkeypatch.setattr(tss, "engine", eng)
        monkeypatch.setattr(tstate, "engine", eng)

        @contextmanager
        def _np():
            with Session(eng) as s:
                yield s

        monkeypatch.setattr(database, "nullpool_session", _np)

        # Projekt + 3 Entries + Snapshot anlegen.
        with Session(eng) as s:
            p = Project(name="b708", path="/tmp/b708")
            s.add(p)
            s.flush()
            pid = p.id
            for i in range(3):
                s.add(TimelineEntry(project_id=pid, track="video", media_id=i + 1,
                                    start_time=i * 5.0, end_time=i * 5.0 + 5.0, lane=0))
            s.commit()

        from services.timeline_snapshot_service import create_snapshot, restore_snapshot
        sid = create_snapshot(pid, "stand-A")

        # Timeline veraendern (damit Restore etwas zu tun hat).
        with Session(eng) as s:
            s.query(TimelineEntry).filter_by(project_id=pid, media_id=1).delete()
            s.commit()

        # Zweiter Writer haelt den Lock ~1.2s.
        started = threading.Event()
        t = threading.Thread(target=_hold_write_lock, args=(db, started, 1.2), daemon=True)
        t.start()
        assert started.wait(3.0), "Lock-Halter-Thread nicht gestartet"

        # Restore parallel — muss trotz gehaltenem Lock am Ende erfolgreich sein.
        restore_snapshot(sid, backup_current=True)
        t.join(timeout=5.0)

        with Session(eng) as s:
            n = s.query(TimelineEntry).filter_by(project_id=pid).count()
        assert n == 3, f"Restore hat Stand-A nicht wiederhergestellt (n={n})"


def test_restore_happy_path_without_contention(tmp_path, monkeypatch):
    """Regressionsschutz: Restore ohne konkurrierenden Writer bleibt korrekt."""
    with _file_engine(tmp_path) as (eng, db):
        import services.timeline_snapshot_service as tss
        import services.timeline_state as tstate
        monkeypatch.setattr(tss, "engine", eng)
        monkeypatch.setattr(tstate, "engine", eng)

        @contextmanager
        def _np():
            with Session(eng) as s:
                yield s

        monkeypatch.setattr(database, "nullpool_session", _np)

        with Session(eng) as s:
            p = Project(name="b708b", path="/tmp/b708b")
            s.add(p)
            s.flush()
            pid = p.id
            for i in range(4):
                s.add(TimelineEntry(project_id=pid, track="video", media_id=i + 1,
                                    start_time=i * 5.0, end_time=i * 5.0 + 5.0, lane=0))
            s.commit()

        from services.timeline_snapshot_service import create_snapshot, restore_snapshot
        sid = create_snapshot(pid, "stand-B")
        with Session(eng) as s:
            s.query(TimelineEntry).filter_by(project_id=pid).delete()
            s.commit()
        restore_snapshot(sid, backup_current=False)
        with Session(eng) as s:
            n = s.query(TimelineEntry).filter_by(project_id=pid).count()
        assert n == 4
