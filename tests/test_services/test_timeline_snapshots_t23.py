"""NEUBAU-VOLLINTEGRATION T2.3 (USE-009/DB-005/DB-016/DB-019):
Timeline-Snapshots produktiv verdrahtet.

Vorher: Service + Tabelle fertig, aber kein Produkt-Caller; Model-Docstring
behauptete faelschlich automatische Persistenz; Versions-Race (DB-016);
detached ORM ueber Session-Grenze (DB-019).
"""
import threading

import pytest
from sqlalchemy.orm import Session

from database.models import Project, TimelineEntry, TimelineSnapshot


@pytest.fixture()
def project(test_engine, monkeypatch):
    import services.timeline_snapshot_service as tss
    import services.timeline_state as tstate
    monkeypatch.setattr(tss, "engine", test_engine)
    monkeypatch.setattr(tstate, "engine", test_engine)
    with Session(test_engine) as s:
        p = Project(name="t23", path="/tmp/t23")
        s.add(p)
        s.flush()
        for i in range(3):
            s.add(TimelineEntry(project_id=p.id, track="video", media_id=i + 1,
                                start_time=i * 5.0, end_time=i * 5.0 + 5.0,
                                lane=0))
        s.commit()
        return p.id


class TestSnapshotService:
    def test_create_and_list_returns_dicts(self, test_engine, project):
        from services.timeline_snapshot_service import create_snapshot, list_snapshots
        sid = create_snapshot(project, "erster")
        snaps = list_snapshots(project)
        assert isinstance(snaps, list) and isinstance(snaps[0], dict)  # DB-019
        assert snaps[0]["id"] == sid
        assert snaps[0]["label"] == "erster"
        assert snaps[0]["clip_count"] == 3

    def test_restore_replaces_entries_and_backs_up(self, test_engine, project):
        from services.timeline_snapshot_service import (
            create_snapshot, list_snapshots, restore_snapshot,
        )
        sid = create_snapshot(project, "stand-A")
        # Timeline veraendern (Clip loeschen)
        with Session(test_engine) as s:
            s.query(TimelineEntry).filter_by(project_id=project,
                                             media_id=1).delete()
            s.commit()
        restore_snapshot(sid, backup_current=True)
        with Session(test_engine) as s:
            n = s.query(TimelineEntry).filter_by(project_id=project).count()
        assert n == 3  # Stand-A wiederhergestellt
        labels = [x["label"] for x in list_snapshots(project)]
        assert any("vor Wiederherstellung" in l for l in labels)  # Backup

    def test_retention_keeps_latest_20(self, test_engine, project, monkeypatch):
        from services import timeline_snapshot_service as tss
        for i in range(25):
            tss.create_snapshot(project, f"s{i}")
        snaps = tss.list_snapshots(project)
        assert len(snaps) == tss.RETENTION_PER_PROJECT
        assert snaps[0]["label"] == "s24"  # neueste behalten

    def test_versions_unique_under_concurrency(self, test_engine, project):
        """DB-016: paralleles Erzeugen darf keine Duplikat-Versionen geben."""
        from services.timeline_snapshot_service import create_snapshot
        errors = []

        def worker(k):
            try:
                create_snapshot(project, f"c{k}")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors
        with Session(test_engine) as s:
            versions = [r[0] for r in s.query(TimelineSnapshot.version)
                        .filter_by(project_id=project).all()]
        assert len(versions) == len(set(versions)), versions

    def test_apply_auto_edit_creates_snapshot(self, test_engine, project, monkeypatch):
        """Kern-Verify (a): Auto-Edit-Apply legt automatisch einen Snapshot an."""
        import services.timeline_service as tls
        from services.timeline_snapshot_service import list_snapshots
        segs = [{"video_id": 1, "start": 0.0, "end": 4.0,
                 "source_start": 0.0, "source_end": 4.0,
                 "crossfade_duration": 0.0}]
        tls.apply_auto_edit_segments(segs, project)
        labels = [x["label"] for x in list_snapshots(project)]
        assert any("Auto-Edit" in l and "(auto)" in l for l in labels), labels


class TestSnapshotMenuUi:
    def test_menu_populates_and_restores(self, test_engine, project, monkeypatch):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])

        from services.timeline_snapshot_service import create_snapshot
        create_snapshot(project, "ui-test")

        import ui.workspaces.schnitt.timeline_shell as shell_mod
        import database as db_mod
        monkeypatch.setattr(db_mod, "get_active_project_id", lambda: project)

        from PySide6.QtWidgets import QWidget

        class _TL(QWidget):
            def __init__(self):
                super().__init__()
                self.loaded = []
            def load_from_db(self, pid): self.loaded.append(pid)

        shell = shell_mod.TimelineShell(timeline=_TL())
        shell._populate_snapshot_menu()
        actions = [a for a in shell._snapshot_menu.actions() if a.isEnabled()]
        assert actions and "ui-test" in actions[0].text()

        actions[0].trigger()
        assert shell.timeline.loaded == [project]
        assert "wiederhergestellt" in shell.status_label.text()
