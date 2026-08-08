"""B-776: Clip-Overuse trotz B-763-Nutzungs-Cap (Rollen-Teilmenge erschoepft).

Livebefund 2026-08-08 (run_id=5, 1414 Segmente, 364 Kandidaten, max_uses=5):
Sections drop/verse/buildup liessen via Rollenmatrix fast nur die
hero-Teilmenge zu (119 von 440 Szenen, struct_clip_tags). Kapazitaet
119 x 5 = 595 < 1264 hero-Segmente -> Stage 3.5 setzte das Cap 789x
komplett aus (usage_cap_forced), der B-768-Soften griff 0x (er laedt nur
filler/unknown nach). 4 Topscorer gewannen 177/177/172/168 Segmente
= 49 % der Timeline; nur 154/364 unique Clips.

Vertraege:
1. Loop wie pacing_service: 220 Segmente, 364 Kandidaten, davon nur 118
   rollen-passend (hero), Rest establishing (NICHT soften-faehig).
   max_uses = ceil(Segmente/Kandidaten)+1 -> kein Clip > max_uses,
   unique deutlich groesser als die 118er-Rollen-Teilmenge.
2. Kernfix sichtbar: rollen-konforme Teilmenge erschoepft + ungecappte
   Kandidaten vorhanden -> rationale usage_cap_role_widened=True,
   usage_cap_forced=False, logger.info mit B-776-Marker; Gewinner ist
   ein ungecappter rollen-fremder Kandidat.
3. usage_cap_forced nur noch, wenn wirklich ALLE Kandidaten am Limit
   sind (echtes Materialdefizit, WARNING mit B-763-Marker bleibt).
4. Rueckwaerts: solange die Rollen-Teilmenge Kapazitaet hat, bleibt die
   Stage-1-Matrix wirksam (kein rollen-fremder Gewinner, kein Flag).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pytest

from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures

RULES_YAML = """\
section_role_matrix:
  drop: [hero, action]
key_mood_gate:
  enabled: false
  forbidden_moods: []
stage1_fallback: soften
"""


def _ctx() -> AudioContext:
    return AudioContext(
        at_timestamp_sec=10.0,
        at_beat_idx=20,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.8,
        at_key="A min",
        at_key_confidence=0.85,
        at_harmonic_tension=0.5,
        at_mood_audio="energetic",
        at_mood_video=None,
        at_genre="techno",
        at_sub_genre=None,
        at_spectral_hash="abc12345",
        at_groove_template="four_on_floor",
        at_lufs=-8.5,
    )


def _clip(clip_id: int, role: str, motion: float = 0.4) -> ClipFeatures:
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=motion,
        embedding=np.ones(4, dtype=np.float32) * 0.5,
    )


@pytest.fixture()
def pipeline(tmp_path):
    rules = tmp_path / "pacing_rules.yaml"
    rules.write_text(RULES_YAML, encoding="utf-8")
    return PacingPipeline(rules_path=rules)


def test_loop_role_minority_does_not_exceed_global_fair_share(pipeline):
    """Vertrag 1: 118 hero von 364 (Rest establishing, nicht soften-faehig),
    220 Segmente -> kein Clip ueber max_uses, unique >> Rollen-Teilmenge."""
    n_segments = 280
    n_total = 364
    n_hero = 118
    candidates = [
        _clip(i, role="hero" if i <= n_hero else "establishing",
              motion=0.8 if i <= 4 else 0.2 + (i % 7) * 0.01)
        for i in range(1, n_total + 1)
    ]
    # wie pacing_service.py Z.1225: ceil(Slots/Videos)+1 -> hier 2
    max_uses = int(math.ceil(n_segments / n_total)) + 1
    # Livebug-Analogie: Rollen-Kapazitaet 118 x 2 = 236 < 280 Segmente —
    # der hero-Pool ist VOR Laufende erschoepft. Ohne Fix setzte Stage 3.5
    # dann das Cap aus und die hero-Topscorer rotierten unbegrenzt.
    assert n_hero * max_uses < n_segments <= n_total * max_uses
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
        f"Ein Clip gewann {worst}x trotz max_uses={max_uses} und "
        f"{n_total} Gesamt-Kandidaten (B-776: Rollen-Teilmenge hebelte "
        f"das Cap aus): top={sorted(wins.values(), reverse=True)[:6]}"
    )
    assert len(wins) >= math.ceil(n_segments / max_uses), (
        f"Nur {len(wins)} verschiedene Clips fuer {n_segments} Segmente"
    )


def test_exhausted_role_pool_widens_instead_of_forcing(pipeline, caplog):
    """Vertrag 2: alle rollen-konformen Kandidaten am Cap + ungecappte
    rollen-fremde vorhanden -> Weitung statt Cap-Aussetzung, Flag + Marker."""
    hero_ids = [1, 2, 3]
    candidates = (
        [_clip(i, role="hero", motion=0.8) for i in hero_ids]
        + [_clip(i, role="establishing", motion=0.3) for i in range(4, 20)]
    )
    max_uses = 2
    usage = {i: max_uses for i in hero_ids}  # hero-Pool erschoepft
    with caplog.at_level(logging.INFO, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            usage_counts=usage,
            max_uses=max_uses,
        )
    assert result.chosen is not None
    assert result.chosen.clip_id not in hero_ids, (
        "Gewinner muss ein ungecappter Kandidat jenseits der Rollenmatrix "
        "sein — nicht ein gecappter hero-Topscorer"
    )
    assert result.rationale.get("usage_cap_role_widened") is True
    assert result.rationale.get("usage_cap_forced") is False, (
        "Cap darf nicht ausgesetzt werden, solange ungecappte Kandidaten "
        "existieren (B-776-Kernfix)"
    )
    assert any("B-776" in rec.getMessage() for rec in caplog.records), (
        "Weitung muss per logger.info mit B-776-Marker sichtbar sein"
    )


def test_cap_forced_only_when_every_candidate_is_capped(pipeline, caplog):
    """Vertrag 3: ALLE Kandidaten am Limit -> echtes Materialdefizit,
    usage_cap_forced=True + B-763-WARNING bleibt (nie leerer Cut)."""
    candidates = [
        _clip(1, role="hero"),
        _clip(2, role="hero"),
        _clip(3, role="establishing"),
    ]
    max_uses = 2
    usage = {1: 2, 2: 2, 3: 2}
    with caplog.at_level(logging.WARNING, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            usage_counts=usage,
            max_uses=max_uses,
        )
    assert result.chosen is not None
    assert result.rationale.get("usage_cap_forced") is True
    assert result.rationale.get("usage_cap_role_widened") is False
    assert any("B-763" in rec.getMessage() for rec in caplog.records)


def test_role_matrix_stays_hard_while_role_pool_has_capacity(pipeline):
    """Vertrag 4 (Rueckwaerts): hero-Pool hat Kapazitaet -> kein Widening,
    kein rollen-fremder Gewinner, Matrix unveraendert wirksam."""
    candidates = (
        [_clip(i, role="hero", motion=0.7) for i in range(1, 11)]
        + [_clip(i, role="establishing", motion=0.9) for i in range(11, 21)]
    )
    result = pipeline.select_best(
        candidates=candidates,
        ctx=_ctx(),
        usage_counts={},
        max_uses=3,
    )
    assert result.chosen is not None
    assert result.chosen.role == "hero"
    assert result.rationale.get("usage_cap_role_widened") is False
    assert result.rationale.get("usage_cap_forced") is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
