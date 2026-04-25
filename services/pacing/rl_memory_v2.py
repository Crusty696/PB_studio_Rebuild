"""D-023 P5: RL-Pacing-Memory v2.

Erweitert das bestehende mem_decision-Schema um:
- User-Verdict-Replay (Truth-Set-Aufbau)
- Per-Section-Acceptance-Rate Aggregation
- Variety-Memory-Integration (FR-S3-3)
- RL-Policy-Update-Hook (FR-S4-2)

Diese Klasse ist die in-memory Reference. Die produktive DB-Variante
nutzt SQLAlchemy auf mem_decision (vorhandenes Schema) + erweitert es
um Verdict-Spalte (Migration P5.1, separat).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Mapping

from services.pacing.rl_policy import SectionPolicy
from services.pacing.variety_memory import VarietyMemory


@dataclass(frozen=True)
class DecisionRecord:
    run_id: int
    cut_id: int
    timestamp_ms: int
    section_type: str
    scene_id: int
    verdict: str | None  # 'good' | 'bad' | None
    reward: float
    components: Mapping[str, float] = field(default_factory=dict)


class RLPacingMemoryV2:
    def __init__(self, variety_window_sec: float = 30.0):
        self._records: list[DecisionRecord] = []
        self._policy = SectionPolicy(min_decisions=1, learning_rate=0.2)
        self._variety = VarietyMemory(window_sec=variety_window_sec)

    def record(self, rec: DecisionRecord) -> None:
        self._records.append(rec)
        # Policy aktualisieren falls Verdict
        if rec.verdict in {"good", "bad"}:
            target_reward = 1.0 if rec.verdict == "good" else 0.0
            self._policy.update(
                section=rec.section_type,
                state=(rec.verdict,),
                reward=target_reward,
            )
        # Variety-Memory pflegen
        self._variety.record(clip_id=rec.scene_id, t_sec=rec.timestamp_ms / 1000.0)

    # ── Aggregations ──────────────────────────────────────────────────────

    def count(self, run_id: int | None = None, verdict: str | None = None) -> int:
        rows = self._records
        if run_id is not None:
            rows = [r for r in rows if r.run_id == run_id]
        if verdict is not None:
            rows = [r for r in rows if r.verdict == verdict]
        return len(rows)

    def section_acceptance_rate(self, section_type: str) -> float:
        rows = [r for r in self._records if r.section_type == section_type and r.verdict in {"good", "bad"}]
        if not rows:
            return 0.5
        good = sum(1 for r in rows if r.verdict == "good")
        return good / len(rows)

    def policy_value(self, section: str, state: tuple) -> float:
        return self._policy.value(section, state)

    def replay(self, run_id: int) -> list[DecisionRecord]:
        return [r for r in self._records if r.run_id == run_id]

    # ── Variety-Memory ────────────────────────────────────────────────────

    def is_clip_recent(self, scene_id: int, t_sec: float) -> bool:
        return self._variety.is_recent(clip_id=scene_id, t_sec=t_sec)

    # ── Truth-Set-Export ──────────────────────────────────────────────────

    def export_truth_set_rows(self) -> list[dict]:
        out = []
        for r in self._records:
            if r.verdict not in {"good", "bad"}:
                continue
            d = asdict(r)
            d["components"] = dict(d["components"])
            out.append(d)
        return out
