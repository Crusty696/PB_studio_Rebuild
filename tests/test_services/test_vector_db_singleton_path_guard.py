"""B-102 / BUG-A3 regression test:

``VectorDBService`` is a process-wide singleton. Earlier ``__new__`` returned
the existing instance and silently ignored a different ``db_path``,
which led to data-integrity bugs (caller thought they were writing to
DB B but actually got DB A).

The fix raises ``ValueError`` when a different ``db_path`` is passed to
an already-initialised singleton. The legitimate project-switch path
goes through ``database.session._patch_service_paths`` which resets
``_instance = None`` first, so this guard does not block it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from services import vector_db_service as vdb_mod
from services.vector_db_service import VectorDBService


@pytest.fixture
def fresh_singleton():
    """Reset the singleton before and after the test so each test starts
    from a clean slate. We do not use ``__new__`` directly here to avoid
    creating an instance that would persist into other tests."""
    vdb_mod._instance = None
    yield
    vdb_mod._instance = None


def test_first_construction_uses_provided_db_path(
    tmp_path: Path, fresh_singleton: None
) -> None:
    """First construction with an explicit db_path uses that path."""
    db_path = tmp_path / "custom.db"
    vdb = VectorDBService(db_path=str(db_path))
    assert Path(vdb.db_path).resolve() == db_path.resolve()


def test_subsequent_construction_without_path_returns_same(
    tmp_path: Path, fresh_singleton: None
) -> None:
    """Subsequent ``VectorDBService()`` (no path) returns the existing
    instance — that is the singleton's whole purpose."""
    db_path = tmp_path / "first.db"
    vdb1 = VectorDBService(db_path=str(db_path))
    vdb2 = VectorDBService()
    assert vdb1 is vdb2
    assert Path(vdb2.db_path).resolve() == db_path.resolve()


def test_subsequent_construction_with_same_path_is_idempotent(
    tmp_path: Path, fresh_singleton: None
) -> None:
    """Constructing again with the SAME db_path is fine (idempotent)."""
    db_path = tmp_path / "same.db"
    vdb1 = VectorDBService(db_path=str(db_path))
    vdb2 = VectorDBService(db_path=str(db_path))
    assert vdb1 is vdb2


def test_subsequent_construction_with_different_path_raises(
    tmp_path: Path, fresh_singleton: None
) -> None:
    """BUG-A3: Constructing with a DIFFERENT db_path on an existing
    singleton must raise ``ValueError`` — it must not silently return
    the old instance with the wrong DB."""
    first_path = tmp_path / "first.db"
    second_path = tmp_path / "second.db"
    VectorDBService(db_path=str(first_path))

    with pytest.raises(ValueError) as excinfo:
        VectorDBService(db_path=str(second_path))

    msg = str(excinfo.value)
    assert "VectorDBService singleton already initialised" in msg
    assert str(second_path.resolve()) in msg or "second.db" in msg


def test_project_switch_via_instance_reset_works(
    tmp_path: Path, fresh_singleton: None
) -> None:
    """The legitimate project-switch path: caller resets ``_instance =
    None`` first, then constructs with a new path. Must succeed."""
    first_path = tmp_path / "project_a.db"
    second_path = tmp_path / "project_b.db"

    VectorDBService(db_path=str(first_path))
    # Mimic database.session._patch_service_paths
    vdb_mod._instance = None

    new_vdb = VectorDBService(db_path=str(second_path))
    assert Path(new_vdb.db_path).resolve() == second_path.resolve()
