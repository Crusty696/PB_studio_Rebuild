"""Tests für services.timeline_snapshot_service.

Pattern: test_engine-Fixture + monkeypatch auf engine in beiden konsumierten Modulen.
"""
import pytest
from sqlalchemy.orm import Session as DBSession
from database.models import Project, TimelineEntry, TimelineSnapshot
from services.timeline_snapshot_service import (
    create_snapshot, list_snapshots, restore_snapshot,
)


def _project_with_clips(test_engine, name="snap-svc"):
    with DBSession(test_engine) as s:
        p = Project(name=name, path=f"/tmp/{name}")
        s.add(p); s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                             start_time=0.0, end_time=2.0, lane=0))
        s.commit()
        return p.id


def _patch_engine(monkeypatch, test_engine):
    """Patche `engine` in beiden konsumierten Modulen."""
    import services.timeline_state as ts_mod
    import services.timeline_snapshot_service as svc_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    monkeypatch.setattr(svc_mod, "engine", test_engine)


def test_create_and_list(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine)
    snap_id = create_snapshot(pid, "first")
    assert snap_id > 0
    snaps = list_snapshots(pid)
    assert len(snaps) == 1
    # DB-019 (NEUBAU-VOLLINTEGRATION T2.3): list_snapshots liefert Dicts
    # statt detached ORM-Objekte (verhindert DetachedInstanceError).
    assert snaps[0]["label"] == "first"
    assert snaps[0]["version"] == 1


def test_create_increments_version(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine, name="snap-svc-2")
    create_snapshot(pid, "v1")
    create_snapshot(pid, "v2")
    snaps = list_snapshots(pid)
    # DB-019: Dict-Zugriff; Reihenfolge ist jetzt version DESC (neueste zuerst).
    versions = sorted(s["version"] for s in snaps)
    assert versions == [1, 2]


def test_restore_replaces_clips(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine, name="snap-svc-3")
    snap_id = create_snapshot(pid, "before-mutation")
    # Mutiere DB
    with DBSession(test_engine) as s:
        s.query(TimelineEntry).filter_by(project_id=pid).delete()
        s.commit()
    # Restore
    restore_snapshot(snap_id)
    with DBSession(test_engine) as s:
        n = s.query(TimelineEntry).filter_by(project_id=pid).count()
        assert n == 1


def test_restore_unknown_id_raises(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    with pytest.raises(ValueError):
        restore_snapshot(99999)


def test_restore_preserves_clip_values(test_engine, monkeypatch):
    """Restore stellt media_id, start_time, end_time, locked korrekt wieder her."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine, name="restore-values")
    snap_id = create_snapshot(pid, "before-mutation")
    # mutiere
    with DBSession(test_engine) as s:
        s.query(TimelineEntry).filter_by(project_id=pid).delete()
        s.commit()
    # restore
    restore_snapshot(snap_id)
    # verify
    with DBSession(test_engine) as s:
        clip = s.query(TimelineEntry).filter_by(project_id=pid).one()
        assert clip.media_id == 1
        assert clip.start_time == 0.0
        assert clip.end_time == 2.0
        assert clip.locked is False


# ---------------------------------------------------------------------------
# T5.9 Coverage-Sweep (E9)
# ---------------------------------------------------------------------------


def test_restore_intermediate_snapshot(test_engine, monkeypatch):
    """v1, v2, v3, restore v2 → DB hat v2-Inhalte (zwei Clips)."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine, name="snap-mid")

    # v1: 1 Clip
    snap_v1 = create_snapshot(pid, "v1")

    # Mutiere → 2 Clips, dann v2
    with DBSession(test_engine) as s:
        s.add(TimelineEntry(project_id=pid, track="video", media_id=2,
                            start_time=2.0, end_time=4.0, lane=0))
        s.commit()
    snap_v2 = create_snapshot(pid, "v2")

    # Mutiere → 3 Clips, dann v3
    with DBSession(test_engine) as s:
        s.add(TimelineEntry(project_id=pid, track="video", media_id=3,
                            start_time=4.0, end_time=6.0, lane=0))
        s.commit()
    create_snapshot(pid, "v3")

    # Mutiere DB beliebig
    with DBSession(test_engine) as s:
        s.query(TimelineEntry).filter_by(project_id=pid).delete()
        s.commit()

    # Restore v2 → DB sollte 2 Clips haben (media_id 1, 2), nicht 3
    restore_snapshot(snap_v2)
    with DBSession(test_engine) as s:
        rows = s.query(TimelineEntry).filter_by(project_id=pid).order_by(TimelineEntry.media_id).all()
    assert len(rows) == 2
    assert [r.media_id for r in rows] == [1, 2]


def test_cascade_on_project_delete(test_engine, monkeypatch):
    """Project-Delete → snapshots werden via CASCADE entfernt."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project_with_clips(test_engine, name="snap-cascade")
    create_snapshot(pid, "v1")
    create_snapshot(pid, "v2")

    with DBSession(test_engine) as s:
        # Vorher: 2 Snapshots
        n_before = s.query(TimelineSnapshot).filter_by(project_id=pid).count()
        assert n_before == 2
        # Hard-Delete des Projekts (cascade test)
        proj = s.get(Project, pid)
        s.delete(proj)
        s.commit()

    with DBSession(test_engine) as s:
        n_after = s.query(TimelineSnapshot).filter_by(project_id=pid).count()
    assert n_after == 0
