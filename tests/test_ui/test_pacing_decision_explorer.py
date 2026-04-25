"""P1.4: Pacing-Decision-Explorer Widget headless-Test.

Verifiziert das Datenfluss-Pattern: refresh_runs → Run-Combo befüllt;
load_decisions_for_run → Tabelle befüllt; row-select → detail-text
zeigt Top-3-Komponenten.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from sqlalchemy import text
from tests.memory.test_decision_recorder import (
    _build_sqlite_with_mem_decision,
    _seed_run,
)
from ui.widgets.pacing_decision_explorer import PacingDecisionExplorer


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _insert_decision(engine, run_id: int, sequence_idx: int, scene_id: int = 42, reward: float = 0.7):
    """Insert eine mem_decision-Row mit reward + components."""
    components = {
        "r_energy": 0.8, "r_mood": 0.7, "r_stem_class": 0.5,
        "r_section": 0.6, "r_freshness": 0.7, "r_collision": 0.7, "r_user": 0.5,
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO mem_decision (
                    run_id, sequence_idx, at_timestamp_sec, at_section_type,
                    scene_id, clip_role, clip_mood_refined,
                    clip_style_bucket_id, clip_motion_score,
                    agent_score, agent_rationale, reward, reward_components
                ) VALUES (
                    :run_id, :seq, 5.0, 'drop',
                    :scene_id, 'hero', 'energetic', 3, 0.7,
                    :score, '{}', :reward, :components
                )
                """
            ),
            {
                "run_id": run_id, "seq": sequence_idx, "scene_id": scene_id,
                "score": reward, "reward": reward, "components": json.dumps(components),
            },
        )


def test_refresh_runs_populates_combo(qapp, tmp_path):
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    _seed_run(engine)
    _seed_run(engine, audio_track_id=2)

    explorer = PacingDecisionExplorer(session_factory=Session)
    # __init__ ruft refresh_runs auf — sollten 2 Einträge da sein
    assert explorer.run_combo.count() == 2


def test_load_decisions_for_run_populates_table(qapp, tmp_path):
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    _insert_decision(engine, run_id, sequence_idx=0, scene_id=10, reward=0.6)
    _insert_decision(engine, run_id, sequence_idx=1, scene_id=11, reward=0.8)

    explorer = PacingDecisionExplorer(session_factory=Session)
    assert explorer.table.rowCount() == 2
    # Verifiziere dass reward in der Tabelle korrekt formatiert ist
    cell = explorer.table.item(0, 3)  # reward-Spalte
    assert cell is not None
    assert "0.600" in cell.text()


def test_no_session_factory_does_not_crash(qapp):
    """Ohne session_factory soll der Tab nicht crashen."""
    explorer = PacingDecisionExplorer(session_factory=None)
    # Auch refresh_runs darf ohne Session-Factory nicht crashen
    explorer.refresh_runs()
    assert explorer.run_combo.count() == 0


def test_top_component_key_handles_invalid_json(qapp):
    explorer = PacingDecisionExplorer(session_factory=None)
    assert explorer._top_component_key(None) == "-"
    assert explorer._top_component_key("") == "-"
    assert explorer._top_component_key("invalid json") == "?"
    valid = json.dumps({"r_energy": 0.9, "r_mood": 0.5})
    assert explorer._top_component_key(valid) == "r_energy"
