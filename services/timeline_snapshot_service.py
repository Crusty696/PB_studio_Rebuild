"""Service für persistente Timeline-Snapshots (Hybrid-Undo). SCHNITT Redesign 2026-05-09.

NEUBAU-VOLLINTEGRATION T2.3 (2026-07-08): Snapshots sind jetzt produktiv
verdrahtet — automatischer Snapshot bei jedem Auto-Edit-Apply
(services/timeline_service.py) + Restore-UI in der Timeline-Shell.
Dazu gefixt: DB-016 (Versions-Race bei max+1 → prozessweiter Lock),
DB-019 (keine detached ORM-Objekte mehr über die Session-Grenze),
Retention (max. 20 Snapshots pro Projekt).
"""
from __future__ import annotations

import json
import logging
import threading
import time as _time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import engine
from database.models import TimelineEntry, TimelineSnapshot
from services.timeline_state import TimelineState

logger = logging.getLogger(__name__)

# DB-016: Die Versionsvergabe liest max(version) und schreibt max+1 ohne
# UNIQUE(project_id, version). Alle Produkt-Writer laufen in DIESEM Prozess
# (UI + Worker) — ein prozessweiter Lock serialisiert die Vergabe ohne
# Schema-Migration. (Multi-Prozess-Schreiber gibt es im Produkt nicht.)
_version_lock = threading.Lock()

RETENTION_PER_PROJECT = 20


def create_snapshot(project_id: int, label: str) -> int:
    """Lädt aktuellen TimelineState und persistiert als Snapshot. Gibt snap.id zurück.

    Hinweis: Snapshots erfassen nur den Cut-State (Clip-Auswahl, Positionen, Locking),
    nicht den Look-State (Crossfade/Brightness/Contrast). Diese Felder werden bei
    restore_snapshot auf Column-Defaults zurückgesetzt.
    """
    with _version_lock:
        state = TimelineState.load(project_id)
        snap_id = state.save_snapshot(label)
        _apply_retention(project_id)
        return snap_id


def _apply_retention(project_id: int, keep: int = RETENTION_PER_PROJECT) -> int:
    """Behaelt die neuesten *keep* Snapshots pro Projekt, loescht Aeltere."""
    with Session(engine) as s:
        rows = (
            s.query(TimelineSnapshot.id)
            .filter_by(project_id=project_id)
            .order_by(TimelineSnapshot.version.desc())
            .offset(keep)
            .all()
        )
        if not rows:
            return 0
        ids = [r[0] for r in rows]
        deleted = (
            s.query(TimelineSnapshot)
            .filter(TimelineSnapshot.id.in_(ids))
            .delete(synchronize_session=False)
        )
        s.commit()
        logger.info(
            "Snapshot-Retention: %d alte Snapshots geloescht (project=%d, keep=%d)",
            deleted, project_id, keep,
        )
        return deleted


def list_snapshots(project_id: int) -> list[dict]:
    """Listet Snapshots eines Projekts (neueste zuerst) als DICTS.

    DB-019-Fix: vorher wurden detached ORM-Objekte über die Session-Grenze
    zurückgegeben — Attributzugriff ausserhalb konnte DetachedInstanceError
    ausloesen. Jetzt: reine Datencontainer.
    """
    with Session(engine) as s:
        rows = (
            s.query(TimelineSnapshot)
            .filter_by(project_id=project_id)
            .order_by(TimelineSnapshot.version.desc())
            .all()
        )
        result: list[dict] = []
        for r in rows:
            try:
                clip_count = len(json.loads(r.payload_json or "[]"))
            except (TypeError, ValueError):
                clip_count = 0
            result.append({
                "id": r.id,
                "version": r.version,
                "label": r.label or "",
                "created_at": str(getattr(r, "created_at", "") or ""),
                "clip_count": clip_count,
            })
        return result


def restore_snapshot(snapshot_id: int, *, backup_current: bool = True) -> None:
    """Stellt Cut-State aus Snapshot wieder her — löscht alle aktuellen
    TimelineEntries des Projekts (auch gelockte) und schreibt die im Payload
    referenzierten Clips neu.

    T2.3: ``backup_current=True`` sichert den aktuellen Stand vorher als
    eigenen Snapshot ("vor Wiederherstellung") — Restore ist damit ohne
    Bestaetigungs-Dialog gefahrlos rueckgaengig machbar.

    Hinweis: nur Cut-State (siehe ClipEntry-Felder in services.timeline_state).
    Crossfade/Brightness/Contrast werden auf Column-Defaults zurückgesetzt.
    raises ValueError bei unbekannter snapshot_id.
    """
    with Session(engine) as s:
        snap = s.get(TimelineSnapshot, snapshot_id)
        if snap is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        project_id = snap.project_id
        version = snap.version
        clips = json.loads(snap.payload_json)

    if backup_current:
        try:
            create_snapshot(project_id, f"vor Wiederherstellung v{version} (auto)")
        except Exception as exc:  # Backup darf Restore nicht verhindern
            logger.warning("Backup-Snapshot vor Restore fehlgeschlagen: %s", exc)

    # B-708: Der Restore war frueher der EINZIGE timeline_entries-Writer ohne die
    # etablierte Anti-Lock-Haertung. apply_auto_edit_segments (timeline_service)
    # schreibt dieselbe Tabelle seit M-12/B-079/B-683 mit
    # _timeline_write_lock + nullpool_session + Retry-auf-"database is locked",
    # alles in EINER Transaktion. Der Restore lief dagegen ueber den geteilten
    # QueuePool ohne Lock/Retry -> gegen einen zweiten prozess-internen
    # Timeline-Writer (paralleler Auto-Edit-Apply/Retention-DELETE) SQLITE_BUSY
    # ("database is locked"), plus mehrsekuendiger Main-Thread-Freeze.
    # Fix: exakt dasselbe Muster wie apply_auto_edit_segments.
    # Lock-Ordnung: backup_current (oben, nutzt _version_lock) ist hier bereits
    # fertig und AUSSERHALB des Write-Locks -> keine Inversion gegen
    # apply_auto_edit_segments (das _timeline_write_lock -> _version_lock haelt).
    # Lazy-Imports: Zyklus-sicher UND respektiert den Test-Monkeypatch von
    # ``database.nullpool_session`` (die conftest-Fixture patcht das Attribut
    # zur Laufzeit; ein Modul-Top-Import wuerde die alte Referenz einfrieren —
    # exakt wie timeline_service._do_apply_segments es macht).
    from database import nullpool_session
    from services.timeline_service import _timeline_write_lock

    max_retries = 5
    for attempt in range(max_retries):
        with _timeline_write_lock:
            try:
                with nullpool_session() as s:
                    s.query(TimelineEntry).filter_by(project_id=project_id).delete()
                    for c in clips:
                        s.add(TimelineEntry(
                            project_id=project_id,
                            track=c["track"],
                            media_id=c["media_id"],
                            start_time=c["start"],
                            end_time=c["end"],
                            lane=c["lane"],
                            source_start=c.get("source_start", 0.0),
                            source_end=c.get("source_end"),
                            locked=c.get("locked", False),
                        ))
                    s.commit()
                break
            except OperationalError as e:
                # Nur "database is locked" ist retrybar; letzter Versuch re-raist.
                if not ("database is locked" in str(e) and attempt < max_retries - 1):
                    raise
                # sonst: aus dem ``with`` fallen (Lock freigeben), dann warten.
        # B-683: Backoff KURZ und AUSSERHALB des Locks.
        wait = 0.5 * (attempt + 1)
        logger.warning(
            "B-708: DB locked bei Snapshot-Restore, Retry %d/%d (warte %.1fs)...",
            attempt + 1, max_retries, wait,
        )
        _time.sleep(wait)

    logger.info(
        "Snapshot v%d wiederhergestellt (project=%d, %d Clips)",
        version, project_id, len(clips),
    )
