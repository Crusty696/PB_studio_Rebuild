"""Slice 4 / FR-S4-2: Per-Section Policy (tabellarische Value-Iteration).

In-Memory-Lookup-Table. Pro Section × State (Tuple-of-Strings) hält die
Policy einen Wert ∈ [0, 1], der über Decisions gelernt wird:

    V ← V + lr * (reward - V)   (Q-Learning ohne next-state)

Für States mit weniger als min_decisions Updates wird default_value
zurückgegeben (Cold-Start-Schutz).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable

State = tuple[Hashable, ...]


@dataclass
class SectionPolicy:
    learning_rate: float = 0.1
    min_decisions: int = 5
    default_value: float = 0.5
    _table: dict[tuple[str, State], float] = field(default_factory=dict)
    _counts: dict[tuple[str, State], int] = field(default_factory=dict)
    _section_counts: dict[str, int] = field(default_factory=dict)

    def value(self, section: str, state: State) -> float:
        key = (section, tuple(state))
        cnt = self._counts.get(key, 0)
        if cnt < self.min_decisions:
            return float(self.default_value)
        return float(self._table[key])

    def update(self, section: str, state: State, reward: float) -> None:
        if not (0.0 <= reward <= 1.0):
            raise ValueError(f"reward must be in [0, 1], got {reward}")
        key = (section, tuple(state))
        prev = self._table.get(key, self.default_value)
        new_value = prev + self.learning_rate * (float(reward) - prev)
        self._table[key] = float(new_value)
        self._counts[key] = self._counts.get(key, 0) + 1
        self._section_counts[section] = self._section_counts.get(section, 0) + 1

    def n_decisions(self, section: str) -> int:
        return int(self._section_counts.get(section, 0))
