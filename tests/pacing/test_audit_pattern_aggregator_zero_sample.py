"""Audit-Regression: gerundete Daempfungs-Gewichte duerfen keine
sample_size=0-Muster erzeugen.

Ein einzelnes run_rating>=4 traegt RUN_RATING_DAMPENING_WEIGHT=0.3 bei.
Der Filter lief auf dem UNGERUNDETEN Wert (0.3 > 0 -> durch), gerundet
wurde erst danach -> PatternUpdate(accept=0, reject=0, sample=0).
wilson_lower_bound(0, 0) gibt per Vertrag 0.5 zurueck und wird als
`confidence` persistiert: eine Nicht-Messung, die in
`brain_actions` (ORDER BY confidence DESC) ueber echt gemessenen Mustern
steht.
"""
from __future__ import annotations

from services.pacing.pattern_aggregator import (
    RUN_RATING_DAMPENING_WEIGHT,
    PatternAggregator,
)
from services.stats.wilson_lower_bound import wilson_lower_bound


def _decision(run_rating: int, scene_id: int = 7) -> dict:
    return {
        "scene_id": scene_id,
        "at_genre": "psytrance",
        "at_section_type": "drop",
        "at_bpm": 140.0,
        "user_verdict": None,
        "user_rating": None,
        "run_rating": run_rating,
    }


def test_wilson_contract_zero_zero_is_neutral_half() -> None:
    # Belegt, warum sample_size=0 schaedlich ist: 0.5 ist keine Messung.
    assert wilson_lower_bound(0, 0) == 0.5


def test_single_run_rating_produces_no_pattern_row() -> None:
    # RED ohne Fix: 1 Update mit accept=0/reject=0/sample=0
    updates = PatternAggregator._aggregate([_decision(5)])
    assert updates == [], f"erwartet keine Muster-Zeile, bekam {updates}"


def test_single_negative_run_rating_produces_no_pattern_row() -> None:
    # RED ohne Fix: 1 Update mit sample=0
    updates = PatternAggregator._aggregate([_decision(1)])
    assert updates == []


def test_no_update_ever_has_zero_sample_size() -> None:
    # RED ohne Fix: die 1er- und 2er-Faelle liefern sample_size == 0
    for n in range(1, 6):
        updates = PatternAggregator._aggregate([_decision(5) for _ in range(n)])
        for u in updates:
            assert u.sample_size > 0, (
                f"n={n} erzeugte sample_size=0 "
                f"(roh={n * RUN_RATING_DAMPENING_WEIGHT})"
            )
            assert u.accept_count + u.reject_count <= u.sample_size


def test_enough_run_ratings_still_aggregate() -> None:
    # Gegenprobe: Evidenz geht nicht verloren, sobald sie auf >=1 rundet.
    updates = PatternAggregator._aggregate([_decision(5) for _ in range(4)])
    assert len(updates) == 1
    assert updates[0].sample_size == 1
    assert updates[0].accept_count == 1


def test_explicit_verdict_path_unaffected() -> None:
    # Gegenprobe: ungedaempfte Signale bleiben unveraendert erhalten.
    d = _decision(3)
    d["user_verdict"] = "accept"
    updates = PatternAggregator._aggregate([d])
    assert len(updates) == 1
    assert updates[0].sample_size == 1
    assert updates[0].accept_count == 1
