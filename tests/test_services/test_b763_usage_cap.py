"""B-763: Studio-Brain-Pfad hat kein globales Nutzungs-Cap.

Livebefund 2026-08-06 (new_test_august, 251 Kandidaten, 1415 Segmente):
5 Clips gewannen je ~280 Segmente (~95 % der Timeline), 246 Clips gingen
leer aus. `pacing_service` berechnet `max_uses_per_video` und pflegt
`usage_counts` (Z. 1210-1212, 1723) — reicht beides aber nur an den
Legacy-Matcher, nicht an `PacingPipeline.select_best`. Der Studio-Brain-
Pfad kennt nur das 3er-Recency-Fenster; Topscorer rotieren als Karussell.

Vertraege:
1. Kandidat am Nutzungs-Cap verliert gegen Alternative unter dem Cap.
2. Alle am Cap: bester gewinnt trotzdem (nie leerer Cut) + rationale-Flag.
3. Ohne max_uses bleibt das Verhalten exakt wie vorher.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures


def _ctx() -> AudioContext:
    return AudioContext(
        at_timestamp_sec=10.0,
        at_beat_idx=20,
        at_section_type="verse",
        at_bpm=128.0,
        at_energy=0.6,
        at_key="A min",
        at_key_confidence=0.85,
        at_harmonic_tension=0.5,
        at_mood_audio="energetic",
        at_mood_video=None,
        at_genre="techno",
        at_sub_genre=None,
        at_spectral_hash="abc12345",
        at_groove_template="four_on_floor",
        at_lufs=-12.5,
    )


def _clip(clip_id: int, motion: float) -> ClipFeatures:
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role="action",
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=motion,
        embedding=np.ones(4, dtype=np.float32) * 0.5,
    )


@pytest.fixture()
def pipeline(tmp_path):
    return PacingPipeline(rules_path=tmp_path / "missing_rules.yaml")


def test_capped_candidate_loses_to_uncapped_alternative(pipeline):
    """Kernvertrag: Cap erzwingt Ausweichen auf ungenutzte Clips."""
    top = _clip(1, motion=0.6)     # passt am besten zur Energie 0.6
    alt = _clip(2, motion=0.2)     # schlechterer Score
    result = pipeline.select_best(
        candidates=[top, alt],
        ctx=_ctx(),
        usage_counts={1: 7, 2: 0},
        max_uses=7,
    )
    assert result.chosen is not None
    assert result.chosen.clip_id == 2, (
        "Kandidat am Nutzungs-Cap (7/7) gewann erneut, obwohl eine "
        "Alternative unter dem Cap existiert"
    )


def test_all_capped_still_picks_best_and_flags(pipeline):
    """Nie leerer Cut: alle am Cap -> bester gewinnt, aber hoerbar."""
    a, b = _clip(1, motion=0.6), _clip(2, motion=0.2)
    result = pipeline.select_best(
        candidates=[a, b],
        ctx=_ctx(),
        usage_counts={1: 7, 2: 7},
        max_uses=7,
    )
    assert result.chosen is not None
    assert result.chosen.clip_id == 1
    assert result.rationale.get("usage_cap_forced") is True, (
        "Ausgesetztes Cap muss im rationale sichtbar sein"
    )


def test_loop_distribution_like_pacing_service(pipeline):
    """End-to-End-Vertrag des echten Auswahl-Loops (pacing_service-Muster):

    Wahl -> usage_counts[vid] += 1 -> naechstes Segment, mit einem
    dominanten Topscorer. Ohne Cap gewann der Topscorer (fast) alles;
    mit Cap darf KEIN Clip oefter als max_uses gewinnen und die Auswahl
    muss sich real verteilen.
    """
    n_segments = 100
    candidates = [_clip(i, motion=0.6 if i == 1 else 0.2 + (i % 7) * 0.01)
                  for i in range(1, 21)]  # 20 Kandidaten, Clip 1 dominiert
    max_uses = (n_segments // len(candidates)) + 1  # = 6, wie pacing_service
    usage: dict[int, int] = {}
    used_recently: list[int] = []
    wins: dict[int, int] = {}
    for _ in range(n_segments):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            recent_clip_ids=used_recently[-3:] or None,
            usage_counts=usage,
            max_uses=max_uses,
        )
        assert result.chosen is not None
        vid = result.chosen.clip_id
        wins[vid] = wins.get(vid, 0) + 1
        usage[vid] = usage.get(vid, 0) + 1
        used_recently.append(vid)
    worst = max(wins.values())
    assert worst <= max_uses, (
        f"Ein Clip gewann {worst}x trotz max_uses={max_uses}: {wins}"
    )
    assert len(wins) >= n_segments // max_uses, (
        f"Nur {len(wins)} verschiedene Clips fuer {n_segments} Segmente: {wins}"
    )


def test_without_max_uses_behavior_unchanged(pipeline):
    """Rueckwaerts-Vertrag: ohne Cap gewinnt weiterhin der Topscorer."""
    a, b = _clip(1, motion=0.6), _clip(2, motion=0.2)
    result = pipeline.select_best(candidates=[a, b], ctx=_ctx())
    assert result.chosen is not None
    assert result.chosen.clip_id == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
