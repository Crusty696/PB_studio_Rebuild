"""Slice 3 / FR-S3-3: Project-Wide Variety-Memory.

Hält pro Run im Speicher fest, wann jede Clip-ID zuletzt verwendet wurde.
Liefert is_recent() + linear-decaying penalty().

DB-Persistierung (mem_decision-SQL-Lookup) ist Slice-3-FE-Vorgang;
diese Klasse ist die in-memory Reference-Implementierung mit derselben
API, sodass sie 1:1 ersetzt werden kann.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VarietyMemory:
    window_sec: float
    _last_used: dict[int, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.window_sec <= 0:
            raise ValueError(f"window_sec must be > 0, got {self.window_sec}")

    def record(self, clip_id: int, t_sec: float) -> None:
        """Markiere Clip-ID als bei t_sec verwendet (überschreibt frühere Werte)."""
        self._last_used[int(clip_id)] = float(t_sec)

    def is_recent(self, clip_id: int, t_sec: float) -> bool:
        """True wenn clip_id < window_sec her benutzt wurde."""
        last = self._last_used.get(int(clip_id))
        if last is None:
            return False
        return (float(t_sec) - last) < self.window_sec

    def penalty(self, clip_id: int, t_sec: float) -> float:
        """Linear decaying penalty ∈ [0, 1]:

        - direkt nach Verwendung: 1.0
        - bei window_sec: 0.0
        - älter: 0.0
        - unbekannt: 0.0
        """
        last = self._last_used.get(int(clip_id))
        if last is None:
            return 0.0
        delta = float(t_sec) - last
        if delta >= self.window_sec or delta < 0:
            return 0.0
        return float(1.0 - (delta / self.window_sec))

    def clear(self) -> None:
        self._last_used.clear()
