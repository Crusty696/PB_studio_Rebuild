"""B-602: Pipeline-Checkpoint muss projekt-relativ sein.

Vorher lag der Checkpoint CWD-global unter ``storage/pipeline_state/<id>.json``
und wurde von allen Projekten mit derselben track_id geteilt. Ein voll
analysiertes Projekt liess ein frisch geoeffnetes zweites Projekt (gleiche
track_id=1) alle Stages ueberspringen -> keine Analyse, Auto-Edit 0 Segmente.

Fix: ``stem_cache._storage_root()`` loest ``database.session.APP_ROOT`` zur
Laufzeit auf (per ``set_project`` mutierbar).
"""
from pathlib import Path

import database.session as db_session
from services.audio_pipeline import stem_cache, checkpoint


def _reset_storage_root_override():
    # Sicherstellen, dass der Test den APP_ROOT-Pfad nimmt, nicht ein
    # gepatchtes _STORAGE_ROOT aus anderem Test-State.
    stem_cache._STORAGE_ROOT = Path("storage")


def test_cache_meta_path_is_project_relative(tmp_path, monkeypatch):
    _reset_storage_root_override()
    proj = tmp_path / "projA"
    proj.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", proj)
    p = stem_cache.cache_meta_path(1)
    assert p == proj / "storage" / "pipeline_state" / "1.json"


def test_checkpoint_does_not_leak_across_projects(tmp_path, monkeypatch):
    """Kern-Regression: Projekt B erbt NICHT die stage-done-Flags von Projekt A."""
    _reset_storage_root_override()
    proj_a = tmp_path / "A"
    proj_b = tmp_path / "B"
    proj_a.mkdir()
    proj_b.mkdir()

    # Projekt A: track_id=1, stem_gen + beat_grid als done markiert
    monkeypatch.setattr(db_session, "APP_ROOT", proj_a)
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")
    checkpoint.mark_stage_done(track_id=1, stage_name="beat_grid")
    assert checkpoint.is_stage_done(track_id=1, stage_name="stem_gen")

    # Projekt B: gleiche track_id=1, frisch -> darf NICHTS von A sehen
    monkeypatch.setattr(db_session, "APP_ROOT", proj_b)
    assert checkpoint.is_stage_done(track_id=1, stage_name="stem_gen") is False
    assert checkpoint.is_stage_done(track_id=1, stage_name="beat_grid") is False

    # A bleibt unberuehrt
    monkeypatch.setattr(db_session, "APP_ROOT", proj_a)
    assert checkpoint.is_stage_done(track_id=1, stage_name="stem_gen") is True


def test_patched_storage_root_still_wins(tmp_path, monkeypatch):
    """Bestehende Unit-Tests patchen _STORAGE_ROOT direkt — muss Vorrang behalten."""
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    # APP_ROOT zeigt woanders hin; der explizite Patch gewinnt trotzdem
    monkeypatch.setattr(db_session, "APP_ROOT", tmp_path / "irrelevant")
    p = stem_cache.cache_meta_path(5)
    assert p == tmp_path / "pipeline_state" / "5.json"
