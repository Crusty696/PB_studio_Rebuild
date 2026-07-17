"""Tests fuer services.brain.paths und services.brain.schemas.*.

Zweck: Pfad-Konvention + Schema-Validierung pruefen, OHNE auf System-
APPDATA zu schreiben (TMP-overlay via monkeypatch).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.brain import paths


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData_Roaming"))
    yield tmp_path


def test_brain_v3_app_dir_creates_under_appdata(isolated_appdata):
    p = paths.brain_v3_app_dir()
    assert p.exists()
    assert p.name == "brain_v3"
    assert p.parent.name == "PB_Studio"
    assert p.is_relative_to(isolated_appdata)


def test_brain_v3_app_dir_separated_from_v1_v2(isolated_appdata):
    """V3-DBs liegen in eigenem Subfolder, NICHT direkt unter PB_Studio/."""
    p = paths.brain_v3_app_dir()
    pb_root = isolated_appdata / "AppData_Roaming" / "PB_Studio"
    assert p == pb_root / "brain_v3"
    # V1/V2 Hypothese-Pfad waere pb_root / "brain" oder pb_root direkt
    assert p != pb_root / "brain"


def test_db_path_helpers(isolated_appdata):
    assert paths.weights_db_path().name == "weights.db"
    assert paths.patterns_db_path().name == "patterns.db"
    assert paths.embedding_cache_db_path().name == "embedding_cache.db"
    # Alle drei im selben Verzeichnis
    assert paths.weights_db_path().parent == paths.embedding_cache_db_path().parent


def test_project_paths_under_project_root(tmp_path: Path):
    proj = tmp_path / "my_project"
    proj.mkdir()
    p = paths.brain_v3_project_dir(proj)
    assert p == proj / "brain_v3"
    assert p.exists()
    assert paths.project_embeddings_db_path(proj).name == "embeddings.db"
    assert paths.project_state_db_path(proj).name == "state.db"
