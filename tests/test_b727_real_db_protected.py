"""B-727: Die Testsuite darf niemals in die reale Projekt-Datenbank schreiben.

Vorfall 2026-07-26: ein Default-Suite-Lauf hat Zeilen in die reale
``pb_studio.db`` im Repo-Root geschrieben (AnalysisStatus fuer die
Test-IDs 99 und 5, inklusive Fehlertext "demucs kaputt"). Ursache war
``tests/test_workers/test_audio_pipeline_v2_worker.py``: der Test patchte
Storage- und Checkpoint-Pfade, aber nicht die globale DB-Engine, und die
``test_engine``-Fixture ist kein ``autouse``.

Der Guard sitzt in ``tests/conftest.py`` (``_protect_real_database``).
Diese Tests sichern ihn gegen Regression ab.
"""
from __future__ import annotations

from pathlib import Path

import database
from database.session import APP_ROOT


def _real_db_path() -> Path:
    return (APP_ROOT / "pb_studio.db").resolve()


def test_global_engine_does_not_point_at_repo_database():
    """Die globale Engine zeigt waehrend der Suite auf eine Temp-DB."""
    active = Path(str(database.engine.url).replace("sqlite:///", "")).resolve()
    assert active != _real_db_path(), (
        "Die globale DB-Engine zeigt auf die reale Projekt-DB "
        f"({active}). Der Guard _protect_real_database in tests/conftest.py "
        "greift nicht mehr."
    )


def test_nullpool_session_does_not_point_at_repo_database():
    """Auch Worker-Writes ueber nullpool_session() landen in der Temp-DB.

    ``_get_cached_nullpool_engine()`` leitet seine URL aus ``engine.url`` ab;
    dieser Test sichert genau diese Kopplung ab — sie ist der Grund, warum
    der Guard den Worker-Schreibpfad ueberhaupt mit abdeckt.
    """
    with database.nullpool_session() as session:
        bound = Path(
            str(session.get_bind().url).replace("sqlite:///", "")
        ).resolve()
    assert bound != _real_db_path(), (
        f"nullpool_session() ist an die reale Projekt-DB gebunden ({bound})."
    )


def test_analysis_status_write_stays_out_of_repo_database():
    """Ein echter AnalysisStatus-Write darf die reale DB nicht veraendern.

    Das ist der konkrete Schreibpfad aus dem Vorfall: der
    AudioPipelineV2Worker meldet Stage-Status ueber diesen Service.
    """
    real_db = _real_db_path()
    before = real_db.stat().st_mtime_ns if real_db.exists() else None

    from services import analysis_status_service

    analysis_status_service.mark_started("audio", 4242, "beat_grid")
    analysis_status_service.mark_done("audio", 4242, "beat_grid")

    after = real_db.stat().st_mtime_ns if real_db.exists() else None
    assert before == after, (
        "Ein AnalysisStatus-Write hat die reale Projekt-DB angefasst "
        f"({real_db})."
    )
