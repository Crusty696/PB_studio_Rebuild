"""Coverage-Guard.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 16 (Tier 2 Building-Blocks)

Pruefen ob Sample-Liste das gesamte Video abdeckt (max-Luecke).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


__all__ = ["CoverageReport", "compute_coverage", "assert_coverage_complete", "IncompleteCoverage"]


class IncompleteCoverage(RuntimeError):
    pass


@dataclass(frozen=True)
class CoverageReport:
    duration_s: float
    sampled_count: int
    max_gap_s: float
    percent_covered: float
    gaps: list[tuple[float, float]] = field(default_factory=list)


def compute_coverage(
    sampled_times: Sequence[float],
    duration_s: float,
    max_gap_s: float = 2.0,
) -> CoverageReport:
    """Berechnet Coverage-Statistiken.

    Args:
        sampled_times: Liste von Sample-Timestamps (unsortiert ok).
        duration_s: Video-Laenge.
        max_gap_s: Schwelle fuer Gap-Listing (kein Throw, nur Listung).

    Returns:
        CoverageReport mit max_gap_s, percent_covered, gaps.
    """
    if duration_s <= 0:
        return CoverageReport(duration_s=duration_s, sampled_count=0,
                              max_gap_s=0.0, percent_covered=0.0, gaps=[])

    if not sampled_times:
        return CoverageReport(
            duration_s=duration_s, sampled_count=0,
            max_gap_s=duration_s, percent_covered=0.0,
            gaps=[(0.0, duration_s)],
        )

    sorted_times = sorted(sampled_times)
    gaps: list[tuple[float, float]] = []
    max_gap = 0.0

    # Gap vor erstem Sample
    if sorted_times[0] > 0:
        gap = sorted_times[0]
        max_gap = max(max_gap, gap)
        if gap > max_gap_s:
            gaps.append((0.0, sorted_times[0]))

    # Gaps zwischen Samples
    for i in range(1, len(sorted_times)):
        gap = sorted_times[i] - sorted_times[i - 1]
        max_gap = max(max_gap, gap)
        if gap > max_gap_s:
            gaps.append((sorted_times[i - 1], sorted_times[i]))

    # Gap nach letztem Sample
    last_to_end = duration_s - sorted_times[-1]
    if last_to_end > 0:
        max_gap = max(max_gap, last_to_end)
        if last_to_end > max_gap_s:
            gaps.append((sorted_times[-1], duration_s))

    # Coverage-Prozent
    covered_s = duration_s - sum(b - a for a, b in gaps)
    percent = 100.0 * covered_s / duration_s

    return CoverageReport(
        duration_s=duration_s,
        sampled_count=len(sorted_times),
        max_gap_s=max_gap,
        percent_covered=percent,
        gaps=gaps,
    )


def assert_coverage_complete(
    sampled_times: Sequence[float],
    duration_s: float,
    max_gap_s: float = 2.0,
    min_percent: float = 99.5,
) -> CoverageReport:
    """Wirft ``IncompleteCoverage`` wenn Coverage-Anforderungen nicht erfuellt.

    Returns: CoverageReport bei Erfolg.
    """
    rep = compute_coverage(sampled_times, duration_s, max_gap_s)
    if rep.max_gap_s > max_gap_s:
        raise IncompleteCoverage(
            f"max gap {rep.max_gap_s:.2f}s > limit {max_gap_s}s "
            f"({len(rep.gaps)} gaps)"
        )
    if rep.percent_covered < min_percent:
        raise IncompleteCoverage(
            f"coverage {rep.percent_covered:.1f}% < min {min_percent}%"
        )
    return rep
