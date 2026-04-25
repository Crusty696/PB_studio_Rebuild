"""D-023 P5: RL-Pacing-Memory v2 (in-memory Reference)."""
import pytest

from services.pacing.rl_memory_v2 import RLPacingMemoryV2, DecisionRecord


def _decision(run_id, cut_id, section, verdict=None, reward=0.5):
    return DecisionRecord(
        run_id=run_id, cut_id=cut_id, timestamp_ms=1000 * cut_id,
        section_type=section, scene_id=42, verdict=verdict, reward=reward,
        components={"r_energy": reward, "r_mood": reward},
    )


def test_record_decision():
    m = RLPacingMemoryV2()
    m.record(_decision(1, 1, "chorus"))
    assert m.count(run_id=1) == 1


def test_record_with_verdict_updates_policy():
    m = RLPacingMemoryV2()
    m.record(_decision(1, 1, "chorus", verdict="good", reward=0.9))
    p = m.policy_value("chorus", state=("good",))
    # Erstes Update: Wert sollte sich vom Default unterscheiden, sobald min_decisions=1
    assert m.count(verdict="good") == 1


def test_aggregate_section_acceptance():
    m = RLPacingMemoryV2()
    for cid, v in [(1, "good"), (2, "good"), (3, "bad"), (4, "good"), (5, None)]:
        m.record(_decision(1, cid, "chorus", verdict=v))
    accept = m.section_acceptance_rate("chorus")
    # 3 good aus 4 mit Verdict (None nicht gezählt)
    assert abs(accept - 0.75) < 1e-6


def test_section_acceptance_no_data():
    m = RLPacingMemoryV2()
    assert m.section_acceptance_rate("chorus") == 0.5  # Default neutral


def test_replay_for_run():
    m = RLPacingMemoryV2()
    m.record(_decision(1, 1, "chorus", verdict="good"))
    m.record(_decision(1, 2, "chorus", verdict="bad"))
    m.record(_decision(2, 1, "chorus", verdict="good"))
    rs = m.replay(run_id=1)
    assert len(rs) == 2
    rs2 = m.replay(run_id=2)
    assert len(rs2) == 1


def test_recent_clip_protection():
    """Variety-Memory-Integration: Clips < 30s rejected."""
    m = RLPacingMemoryV2(variety_window_sec=30.0)
    m.record(_decision(1, 1, "chorus"))
    assert m.is_clip_recent(scene_id=42, t_sec=15.0)
    assert not m.is_clip_recent(scene_id=42, t_sec=31.0)
    assert not m.is_clip_recent(scene_id=999, t_sec=15.0)


def test_export_for_truth_set():
    m = RLPacingMemoryV2()
    m.record(_decision(1, 1, "chorus", verdict="good", reward=0.85))
    rows = m.export_truth_set_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "good"
    assert row["section_type"] == "chorus"
    assert "components" in row


def test_export_skips_no_verdict_rows():
    m = RLPacingMemoryV2()
    m.record(_decision(1, 1, "chorus", verdict=None))
    m.record(_decision(1, 2, "chorus", verdict="good"))
    rows = m.export_truth_set_rows()
    assert len(rows) == 1
    assert rows[0]["cut_id"] == 2
