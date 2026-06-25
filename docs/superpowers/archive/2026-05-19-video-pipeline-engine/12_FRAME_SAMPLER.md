# 12 — Frame-Sampler-Primitive

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Liefert Frame-Timestamps nach Strategie. Garantiert Coverage.

## Strategien

| Modus | Beschreibung | Coverage |
|---|---|---|
| `uniform(rate_s)` | alle X Sekunden | hoch |
| `scene_anchored(scenes, k=3)` | k Frames pro Szene (Anfang/Mitte/Ende) | szenenbezogen |
| `dense_until(n_max)` | alle Frames bis n_max | voll, nur kurze Clips |
| `mixed(uniform=2s, scene_extra=3)` | Default Maximum-Quality | Coverage-Garantie + Szenen-Anker |

## Scope

```python
def sample_frame_times(duration_s: float, fps: float,
                       strategy: str, scenes: list[Scene] | None = None,
                       **kwargs) -> list[float]: ...
```

## Verifikation

- Coverage-Map ohne Loch > 2 s im Mixed-Modus
- Anzahl Samples plausibel
- `pytest tests/test_services/test_frame_sampler.py -v` gruen
