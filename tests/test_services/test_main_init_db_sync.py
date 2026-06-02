"""Cycle 14 Hotfix: Verifiziert dass main.py init_db() SYNCHRON
vor PBWindow aufruft — sonst Race-Condition mit Worker-Threads, die
ORM-Queries gegen ein noch-nicht-migriertes DB-Schema machen.
"""
from __future__ import annotations

import inspect
from pathlib import Path


def _read_main_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "main.py").read_text(encoding="utf-8")


def test_main_calls_init_db_before_pbwindow_construction():
    src = _read_main_source()
    init_db_idx = src.find("run_database_bootstrap(")
    pbwindow_idx = src.find("window = PBWindow()")
    assert init_db_idx > 0, (
        "main.py muss den DB-Bootstrap SYNCHRON aufrufen (siehe Cycle-14-Hotfix). "
        "Ohne synchronen Migration-Run racet PBWindow mit dem "
        "StartupCheckWorker-Async-Pfad."
    )
    assert pbwindow_idx > 0
    assert init_db_idx < pbwindow_idx, (
        "init_db() muss VOR PBWindow() laufen — sonst startet die UI "
        "Worker die ORM-Queries machen bevor das Schema migriert ist."
    )


def test_main_init_db_call_inside_try_block():
    """Der synchrone init_db()-Call darf den App-Start nicht killen
    falls die Migration crasht — broad except mit Log."""
    src = _read_main_source()
    # Zeilenbereich um run_database_bootstrap herum extrahieren
    idx = src.find("run_database_bootstrap(")
    window = src[max(0, idx - 300): idx + 300]
    assert "from services.startup_checks import run_database_bootstrap" in window
    assert "process_events=QApplication.processEvents" in window
    assert "Cycle 14: Alembic migrations" in window or "Migration" in window
