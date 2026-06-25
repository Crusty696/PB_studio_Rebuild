# 16 — Coverage-Guard

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Stelle sicher dass jede Sekunde des Videos analysiert wurde. Vor `status=done`.

## Scope

```python
def assert_coverage(sampled_times: list[float], duration_s: float,
                    max_gap_s: float = 2.0) -> CoverageReport:
    """
    Returns CoverageReport(percent_covered, max_gap_s, gaps: list[(start, end)]).
    Hebt IncompleteAnalysis wenn percent_covered < 99.5 oder max_gap_s > limit.
    """
```

- Pro Stage eigene Coverage-Map (Scene, Keyframe, SigLIP-Embed, RAFT-Motion).
- Vor Stage-Done: Guard pruefen.
- Bei Fail: Stage bleibt `partial`, Resume-Checkpoint zeigt Luecken.

## Verifikation

- Synthetic-Loch > 2 s → Guard meldet
- Lueckenlose Coverage → Guard ok
- `pytest tests/test_services/test_coverage_guard.py -v` gruen
