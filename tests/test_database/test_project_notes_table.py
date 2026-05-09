"""SCHNITT-Redesign Task 1.3: ProjectNote-Tabelle.

Verifiziert dass die ``project_notes``-Tabelle existiert, ein Default-
Insert funktioniert und der UNIQUE-Constraint auf ``project_id`` einen
zweiten Insert pro Projekt blockiert. Nutzt die conftest-Fixture
``test_engine`` (In-Memory SQLite mit FK-Pragma) wie Task 1.1 / 1.2.
"""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Project, ProjectNote


def test_project_notes_table_exists(test_engine):
    tables = inspect(test_engine).get_table_names()
    assert "project_notes" in tables


def test_project_notes_default_empty_content(test_engine):
    with Session(test_engine) as s:
        p = Project(name="notes-default", path="/tmp/notes-default")
        s.add(p)
        s.flush()
        n = ProjectNote(project_id=p.id)
        s.add(n)
        s.commit()
        s.refresh(n)
        assert n.content_md == ""
        assert n.updated_at is not None


def test_project_notes_unique_per_project(test_engine):
    with Session(test_engine) as s:
        p = Project(name="notes-unique", path="/tmp/notes-unique")
        s.add(p)
        s.flush()
        s.add(ProjectNote(project_id=p.id, content_md="first"))
        s.commit()
        s.add(ProjectNote(project_id=p.id, content_md="second"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_project_notes_cascade_on_project_delete(test_engine):
    """FK ON DELETE CASCADE: Projekt-Hard-Delete entfernt Notes."""
    with Session(test_engine) as s:
        p = Project(name="notes-cascade", path="/tmp/notes-cascade")
        s.add(p)
        s.flush()
        s.add(ProjectNote(project_id=p.id, content_md="will be cascaded"))
        s.commit()
        assert s.query(ProjectNote).count() == 1
        s.delete(p)
        s.commit()
        assert s.query(ProjectNote).count() == 0
