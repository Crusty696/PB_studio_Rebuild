"""B-777: Direkte Wiederholungen umgehen Stage 3.6 (Cap-Zweig schrumpft Pool).

Livebefund 2026-08-08 (run_id=6, nach B-776-Fix d771650): 10 direkte
Rueckenan-Ruecken-Wiederholungen gleicher media_id (1x clip 254 bei
t=1406-1411s, 9x clips 85/86/207/327/328 bei t=4879-4952s). Muster jedes
Paars identisch (mem_decision):

1. Cut N: rollen-konforme hero-Kandidaten alle am Cap -> B-776-Weitung,
   Gewinner ist ein establishing-Clip (Szene 0-4s, unter Cap).
2. Cut N+1: clip_offset des Gewinners steht auf ~4s -> der Caller reicht
   jetzt dessen HERO-Szene (4-10s) als ClipFeatures -> derselbe Clip ist
   ploetzlich der EINZIGE rollen-konforme Kandidat unter dem Cap.
   Stage 3.5 (Zweig "uncapped < survivors") warf alle gecappten
   Alternativen raus, Stage 3.6 stand mit survivors == {previous} da —
   obwohl ~96 ungecappte Weitungs-Kandidaten existierten -> 10x
   adjacency_forced + WARNING statt Alternative.

Vertraege:
1. Kern-Reproduktion: previous ist einziger Pool-Survivor, aber ungecappte
   Kandidaten jenseits der Rollenmatrix existieren -> Pool wird geweitet,
   Gewinner != previous, rationale adjacency_pool_widened=True,
   adjacency_forced=False, logger.info mit B-777-Marker, keine WARNING.
2. Echt alternativlos (einziger Kandidat ueberhaupt = previous) ->
   adjacency_forced=True + B-759-WARNING bleibt (nie leerer Cut).
3. Loop mit Rollen-Minderheit am Cap (Weitung erzwungen): KEIN direktes
   clip_id-Nachbar-Paar im Ergebnis, ausser der jeweilige Cut traegt
   adjacency_forced=True.
4. Die B-777-Weitung respektiert das Cap: sind alle Nicht-Vorgaenger am
   Limit, bleibt adjacency_forced (kein Cap-Bruch durch die Hintertuer).
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


def test_lone_uncapped_role_survivor_widens_instead_of_repeating(
    pipeline, caplog
):
    """Vertrag 1: Live-Muster run_id=6 — previous (hero, unter Cap) ist nach
    dem Cap-Zweig einziger Survivor, 10 establishing-Clips unter Cap
    existieren -> Weitung statt direkter Wiederholung."""
    max_uses = 5
    previous_id = 10
    capped_hero_ids = [1, 2, 3]
    candidates = (
        [_clip(i, role="hero", motion=0.8) for i in capped_hero_ids]
        + [_clip(previous_id, role="hero", motion=0.9)]
        + [_clip(i, role="establishing", motion=0.3) for i in range(11, 21)]
    )
    usage = {i: max_uses for i in capped_hero_ids}
    usage[previous_id] = 1  # unter Cap — genau der Livebefund
    with caplog.at_level(logging.INFO, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            recent_clip_ids=[previous_id],
            usage_counts=usage,
            max_uses=max_uses,
        )
    assert result.chosen is not None
    assert result.chosen.clip_id != previous_id, (
        "B-777: direkter Vorgaenger darf nicht wiederholt werden, solange "
        "ungecappte Alternativen im Gesamt-Kandidatensatz existieren"
    )
    assert result.rationale.get("adjacency_pool_widened") is True
    assert result.rationale.get("adjacency_forced") is False
    assert any("B-777" in rec.getMessage() for rec in caplog.records), (
        "Weitung muss per logger.info mit B-777-Marker sichtbar sein"
    )
    assert not any(
        rec.levelno >= logging.WARNING and "B-759" in rec.getMessage()
        for rec in caplog.records
    ), "Keine B-759-WARNING, wenn Alternativen existieren"


def test_truly_no_alternative_still_forces_adjacency(pipeline, caplog):
    """Vertrag 2: einziger Kandidat ueberhaupt == previous -> Regel wird wie
    bisher ausgesetzt (nie leerer Cut), WARNING mit B-759-Marker."""
    candidates = [_clip(10, role="hero", motion=0.8)]
    with caplog.at_level(logging.WARNING, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            recent_clip_ids=[10],
        )
    assert result.chosen is not None
    assert result.chosen.clip_id == 10
    assert result.rationale.get("adjacency_forced") is True
    assert result.rationale.get("adjacency_pool_widened") is False
    assert any("B-759" in rec.getMessage() for rec in caplog.records)


def test_loop_with_forced_widening_has_no_unflagged_direct_repeats(pipeline):
    """Vertrag 3: Rollen-Minderheit am Cap erzwingt Weitung ueber viele Cuts —
    kein clip_id-Nachbar-Paar im Ergebnis ohne adjacency_forced-Flag."""
    n_segments = 60
    n_total = 24
    n_hero = 3
    candidates = [
        _clip(i, role="hero" if i <= n_hero else "establishing",
              motion=0.8 if i <= n_hero else 0.2 + (i % 7) * 0.01)
        for i in range(1, n_total + 1)
    ]
    max_uses = int(math.ceil(n_segments / n_total)) + 1  # -> 4
    # hero-Kapazitaet 3 x 4 = 12 << 60 Segmente -> Weitung ist erzwungen
    assert n_hero * max_uses < n_segments <= n_total * max_uses
    usage: dict[int, int] = {}
    used_recently: list[int] = []
    widened_seen = 0
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
        if used_recently and vid == used_recently[-1]:
            assert result.rationale.get("adjacency_forced") is True, (
                f"Direkte Wiederholung von clip_id={vid} ohne "
                f"adjacency_forced-Flag (B-777)"
            )
        if result.rationale.get("usage_cap_role_widened"):
            widened_seen += 1
        usage[vid] = usage.get(vid, 0) + 1
        used_recently.append(vid)
    assert widened_seen > 0, (
        "Szenario muss die B-776-Weitung real erzwingen, sonst testet der "
        "Loop den B-777-Pfad nicht"
    )


def test_adjacency_widening_respects_usage_cap(pipeline, caplog):
    """Vertrag 4: alle Nicht-Vorgaenger am Cap -> Weitung darf sie NICHT
    aufnehmen, Wiederholung bleibt als adjacency_forced sichtbar."""
    max_uses = 2
    previous_id = 10
    candidates = (
        [_clip(previous_id, role="hero", motion=0.9)]
        + [_clip(i, role="establishing", motion=0.3) for i in (11, 12)]
    )
    usage = {previous_id: 1, 11: max_uses, 12: max_uses}
    with caplog.at_level(logging.WARNING, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            recent_clip_ids=[previous_id],
            usage_counts=usage,
            max_uses=max_uses,
        )
    assert result.chosen is not None
    assert result.chosen.clip_id == previous_id
    assert result.rationale.get("adjacency_forced") is True
    assert result.rationale.get("adjacency_pool_widened") is False
    assert any("B-759" in rec.getMessage() for rec in caplog.records)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
