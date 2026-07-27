"""Regression: B-721 (Engine-Swap trotz create_all-Fehler) + B-722 (paralleler
Checkpoint-Write verliert Stage-Fortschritt).

B-721: ``database.session.set_project`` loggte einen fehlgeschlagenen
``Base.metadata.create_all`` nur als Warnung und swappte die Engine trotzdem.
Danach zeigten ``engine`` und ``APP_ROOT`` auf einen Stand ohne initialisierte
Tabellen.

B-722: ``services.audio_pipeline.checkpoint.mark_stage_done`` machte ein
ungeschuetztes load->append->save und schrieb ueber den GETEILTEN Temp-Namen
``<track_id>.json.tmp`` (WinError 32 bei zwei Writern, ausserdem lost update).
"""
from __future__ import annotations

import os
import threading
import time

import pytest


# ---------------------------------------------------------------------------
# B-721
# ---------------------------------------------------------------------------

def _no_running_tasks(monkeypatch, ses) -> None:
    monkeypatch.setattr(ses, "_running_tasks_block_reason", lambda **_kw: None)


def test_b721_no_swap_when_create_all_fails(tmp_path, monkeypatch):
    """RED ohne Fix: Engine + APP_ROOT wandern trotz create_all-Fehler mit."""
    import database.session as ses
    from database.models import Base

    _no_running_tasks(monkeypatch, ses)
    original_root = ses.APP_ROOT
    original_url = str(ses.engine.url)

    proj = tmp_path / "proj_broken"
    proj.mkdir()

    def _boom(_engine):
        raise RuntimeError("create_all kaputt")

    monkeypatch.setattr(Base.metadata, "create_all", _boom)
    try:
        with pytest.raises(RuntimeError, match="Tabellen-Initialisierung"):
            ses.set_project(proj)
        assert ses.APP_ROOT == original_root
        assert str(ses.engine.url) == original_url
    finally:
        monkeypatch.undo()
        ses.set_project(original_root, force=True)


def test_b721_force_recovery_path_still_swaps(tmp_path, monkeypatch):
    """Guard (vor UND nach dem Fix gruen): der B-051-Rollback mit force=True
    muss auch bei create_all-Fehler swappen — sonst bleibt die App auf der
    halb-initialisierten neuen DB haengen."""
    import database.session as ses
    from database.models import Base

    _no_running_tasks(monkeypatch, ses)
    original_root = ses.APP_ROOT

    proj = tmp_path / "proj_force"
    proj.mkdir()

    def _boom(_engine):
        raise RuntimeError("create_all kaputt")

    monkeypatch.setattr(Base.metadata, "create_all", _boom)
    try:
        ses.set_project(proj, force=True)
        assert ses.APP_ROOT == proj
    finally:
        monkeypatch.undo()
        ses.set_project(original_root, force=True)


# ---------------------------------------------------------------------------
# B-722
# ---------------------------------------------------------------------------

def test_b722_parallel_mark_stage_done_keeps_all_stages(tmp_path, monkeypatch):
    """RED ohne Fix: der zweite Writer ueberschreibt stages_done des ersten.

    ``load_cache_meta`` wird kuenstlich verlangsamt, damit das Read-Modify-
    Write-Fenster deterministisch ueberlappt.
    """
    from services.audio_pipeline import stem_cache, checkpoint

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    real_load = stem_cache.load_cache_meta

    def slow_load(track_id):
        meta = real_load(track_id)
        time.sleep(0.4)
        return meta

    monkeypatch.setattr(stem_cache, "load_cache_meta", slow_load)

    errors: list[BaseException] = []

    def run(stage: str) -> None:
        try:
            checkpoint.mark_stage_done(99, stage)
        except BaseException as exc:  # noqa: BLE001 — Testdiagnose
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(s,))
        for s in ("stem_gen", "beat_grid")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"Writer-Fehler: {errors}"
    monkeypatch.setattr(stem_cache, "load_cache_meta", real_load)
    assert sorted(checkpoint.stages_done(99)) == ["beat_grid", "stem_gen"]


def test_b722_tmp_name_is_process_unique(tmp_path, monkeypatch):
    """RED ohne Fix: geschrieben wird ueber den geteilten ``<id>.json.tmp``.

    Genau dieser feste Name laesst zwei gleichzeitige Writer auf Windows mit
    WinError 32 kollidieren.
    """
    from services.audio_pipeline import stem_cache, checkpoint

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)

    seen: list[str] = []
    real_replace = os.replace

    def spy_replace(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)
    checkpoint.mark_stage_done(7, "lufs")

    assert seen, "kein atomarer Write beobachtet"
    assert str(os.getpid()) in seen[0], f"geteilter Temp-Name: {seen[0]}"
    final = stem_cache.cache_meta_path(7)
    assert final.exists()
    assert not final.with_suffix(final.suffix + ".tmp").exists()
