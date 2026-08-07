"""B-768: Stage-1-Rollenmatrix kollabiert die Kandidatenmenge.

Livebefund 2026-08-07 00:57 (fullstack_usertest2, 364 Kandidaten): wegen
B-729 tragen fast alle Clips role=unknown/filler. Fuer DROP-Sections
(matrix: [hero, action]) ueberleben Stage 1 nur ~22 Clips, teils 1.
`stage1_fallback=="soften"` griff erst bei 0 Ueberlebenden — Cap (B-763)
und Nachbarschaftsregel (B-759) hatten keine Alternativen mehr:
63 Clips, 334x-Spitzenreiter, 104 direkte Wiederholungen.

Vertraege:
1. Loop wie pacing_service: 100 Segmente, 100 Kandidaten (nur 5 rollen-
   passend), max_uses gesetzt -> Auswahl darf NICHT auf die 5 kollabieren;
   kein Clip > max_uses solange die Gesamt-Kandidatenmenge es hergibt.
2. Kernfix: < STAGE1_MIN_SURVIVORS Ueberlebende + weitere Kandidaten
   vorhanden -> soften BEVOR Cap/Nachbarschaft aussetzen muessen,
   sichtbar via logger.info mit B-768-Marker + rationale-Flag.
3. Rueckwaerts: genug rollen-passende Kandidaten -> kein Soften, unknown
   bleibt draussen (Stage-1-Matrix unveraendert wirksam).

B-729 (Rollen-Klassifikation liefert unknown/filler) bleibt offen —
hier wird nur der Pipeline-Kollaps behandelt, nicht die Datenursache.
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pytest

from services.pacing.pipeline import PacingPipeline, STAGE1_MIN_SURVIVORS
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


def test_loop_does_not_collapse_onto_role_matching_minority(pipeline):
    """Vertrag 1: 5 von 100 rollen-passend -> Loop darf nicht auf die 5
    kollabieren; kein Clip > max_uses, echte Vielfalt wie im B-763-Loop."""
    n_segments = 100
    candidates = [
        _clip(i, role="action" if i <= 5 else "unknown",
              motion=0.8 if i <= 5 else 0.2 + (i % 7) * 0.01)
        for i in range(1, 101)
    ]
    max_uses = (n_segments // len(candidates)) + 1  # = 2, wie pacing_service
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
        f"Ein Clip gewann {worst}x trotz max_uses={max_uses} und 100 "
        f"Gesamt-Kandidaten (Stage-1-Kollaps auf Rollen-Minderheit): {wins}"
    )
    assert len(wins) >= math.ceil(n_segments / max_uses), (
        f"Nur {len(wins)} verschiedene Clips fuer {n_segments} Segmente: {wins}"
    )


def test_soften_triggers_below_min_survivors_with_marker(pipeline, caplog):
    """Vertrag 2: < STAGE1_MIN_SURVIVORS Ueberlebende + weitere Kandidaten
    -> soften (Rollenmenge erweitert) + logger.info mit B-768-Marker."""
    n_matching = 3
    assert n_matching < STAGE1_MIN_SURVIVORS
    candidates = [
        _clip(i, role="action" if i <= n_matching else "unknown")
        for i in range(1, 21)
    ]
    with caplog.at_level(logging.INFO, logger="services.pacing.pipeline"):
        result = pipeline.select_best(candidates=candidates, ctx=_ctx())
    assert result.chosen is not None
    assert result.rationale.get("stage1_softened") is True, (
        "Bei 3 Ueberlebenden von 20 muss gesoftet werden, nicht erst bei 0"
    )
    unknown_pass = [
        sr for sr in result.rationale["stage_results"]
        if sr["clip_id"] > n_matching and sr["passed_stage1"]
    ]
    assert unknown_pass, "Soften muss unknown-Kandidaten in Stage 1 aufnehmen"
    assert any("B-768" in rec.getMessage() for rec in caplog.records), (
        "Soften-Trigger muss per logger.info mit B-768-Marker sichtbar sein"
    )


def test_no_soften_when_enough_role_matching_candidates(pipeline):
    """Vertrag 3 (Rueckwaerts): genug rollen-passende Kandidaten ->
    Matrix bleibt hart, unknown bleibt draussen, kein soften-Flag."""
    n_matching = STAGE1_MIN_SURVIVORS + 2
    candidates = [
        _clip(i, role="action" if i <= n_matching else "unknown")
        for i in range(1, n_matching + 5)
    ]
    result = pipeline.select_best(candidates=candidates, ctx=_ctx())
    assert result.chosen is not None
    assert result.chosen.role == "action"
    assert result.rationale.get("stage1_softened") is False
    for sr in result.rationale["stage_results"]:
        if sr["clip_id"] > n_matching:
            assert sr["passed_stage1"] is False, (
                "unknown darf bei ausreichender Rollen-Abdeckung nicht "
                "durch Stage 1 rutschen"
            )


def test_soften_noop_when_no_widenable_roles_exist(pipeline):
    """Grenzfall: wenige Ueberlebende, aber Rest ist weder filler noch
    unknown -> kein soften-Flag, Matrix-Ablehnung bleibt bestehen."""
    candidates = [
        _clip(1, role="action"),
        _clip(2, role="establishing"),
        _clip(3, role="ambient"),
    ]
    result = pipeline.select_best(candidates=candidates, ctx=_ctx())
    assert result.chosen is not None
    assert result.chosen.clip_id == 1
    assert result.rationale.get("stage1_softened") is False


# ── B-759 in select_best: harte Nachbarschaftsregel (Stage 3.6) ──────────
# E2E-Abnahme 2026-08-07 belegte: die harte B-759-Regel existierte NUR im
# Legacy-Matcher (_drop_direct_predecessor, pacing_edit_helpers.py) — der
# Studio-Brain-Pfad hatte nur den weichen w_freshness=0.05-Term.


def test_direct_predecessor_loses_despite_topscore(pipeline):
    """Direkter Vorgaenger (recent_clip_ids[-1]) verliert trotz Topscore,
    solange eine Alternative ueberlebt."""
    top = _clip(1, role="action", motion=0.8)   # Topscore bei energy=0.8
    alt = _clip(2, role="action", motion=0.2)
    result = pipeline.select_best(
        candidates=[top, alt],
        ctx=_ctx(),
        recent_clip_ids=[1],
    )
    assert result.chosen is not None
    assert result.chosen.clip_id == 2, (
        "Direkter Vorgaenger gewann erneut, obwohl eine Alternative "
        "existiert — harte B-759-Regel fehlt in select_best"
    )
    assert result.rationale.get("adjacency_forced") is False


def test_single_candidate_wins_with_adjacency_warning(pipeline, caplog):
    """Nie leerer Cut: einziger Kandidat = direkter Vorgaenger gewinnt
    trotzdem, aber hoerbar (WARNING mit B-759-Marker) + rationale-Flag."""
    only = _clip(1, role="action")
    with caplog.at_level(logging.WARNING, logger="services.pacing.pipeline"):
        result = pipeline.select_best(
            candidates=[only],
            ctx=_ctx(),
            recent_clip_ids=[1],
        )
    assert result.chosen is not None
    assert result.chosen.clip_id == 1
    assert result.rationale.get("adjacency_forced") is True, (
        "Ausgesetzte Nachbarschaftsregel muss im rationale sichtbar sein"
    )
    assert any("B-759" in rec.getMessage() for rec in caplog.records), (
        "Aussetzung muss per logger.warning mit B-759-Marker hoerbar sein"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
