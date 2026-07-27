"""Audit-Regression: VariationsBudget darf die Run-Historie nicht unbegrenzt
wachsen lassen.

``allow()`` summiert je Bucket-Key ueber die GESAMTE ``_history``-Liste, und
zwar einmal pro Kandidat. ``record()`` hing pro Cut je Key einen Eintrag an,
ohne je zu beschneiden — obwohl das groesste Fenster 45 s umfasst.
``segment_boundary()`` waere der Reset, wird aber von keinem Produktivpfad
aufgerufen. Ergebnis: Aufwand quadratisch in der Mix-Laenge (zusaetzlich
scannt ``PacingPipeline._which_budgets_failed`` dieselbe Liste noch einmal
pro abgelehntem Kandidaten).

Der Test prueft (a) die Wachstumsschranke und (b) dass sich das Ergebnis von
``allow()`` durch das Beschneiden nicht aendert.
"""
from __future__ import annotations

import random

from services.pacing.variations_budget import BudgetRule, VariationsBudget


def test_history_stays_bounded_by_window() -> None:
    # RED ohne Fix: len(_history["role"]) == 2000
    b = VariationsBudget()
    # 2000 Cuts im 0.5-s-Raster = 1000 s Mix. Groesstes Fenster: 45 s.
    for i in range(2000):
        t = i * 0.5
        buckets = {
            "scene_id": i % 50,
            "style_bucket": i % 7,
            "mood_refined": i % 3,
            "role": "hero",
        }
        b.allow(t, buckets)
        b.record(t, buckets)

    for key, rule in VariationsBudget.DEFAULT_BUDGETS.items():
        entries = b._history[key]
        # Bei 0.5 s Cut-Abstand passen hoechstens window_sec/0.5 + 1 Eintraege
        # ins lebende Fenster.
        max_alive = int(rule.window_sec / 0.5) + 2
        assert len(entries) <= max_alive, (
            f"{key}: {len(entries)} Eintraege, erwartet <= {max_alive}"
        )


def test_pruning_does_not_change_allow_results() -> None:
    """Gegenprobe: identische allow()-Antworten mit und ohne Beschneiden."""
    rules = {
        "scene_id": BudgetRule(max_per_window=1, window_sec=45.0),
        "style_bucket": BudgetRule(max_per_window=3, window_sec=30.0),
        "mood_refined": BudgetRule(max_per_window=4, window_sec=30.0),
        "role": BudgetRule(max_per_window=5, window_sec=30.0),
    }
    rng = random.Random(1234)
    seq = []
    t = 0.0
    for _ in range(600):
        t += rng.uniform(0.2, 2.0)
        seq.append((t, {
            "scene_id": rng.randrange(12),
            "style_bucket": rng.randrange(4),
            "mood_refined": rng.randrange(3),
            "role": rng.choice(["hero", "detail", "filler"]),
        }))

    pruning = VariationsBudget(rules)
    # Referenz: dieselbe Klasse, Beschneiden neutralisiert.
    reference = VariationsBudget(rules)
    reference._prune_expired = lambda key, t: None  # type: ignore[assignment]

    for t_i, buckets in seq:
        a = pruning.allow(t_i, buckets)
        c = reference.allow(t_i, buckets)
        assert a == c, f"Divergenz bei t={t_i}: pruned={a} full={c}"
        if a:
            pruning.record(t_i, buckets)
            reference.record(t_i, buckets)

    assert len(reference._history["role"]) > len(pruning._history["role"]), (
        "Referenz muss mehr Eintraege halten, sonst testet der Vergleich nichts"
    )


def test_out_of_order_record_keeps_history() -> None:
    """Rueckwaerts nachgetragene Zeitstempel duerfen nichts wegwerfen."""
    b = VariationsBudget({"role": BudgetRule(max_per_window=5, window_sec=10.0)})
    b.record(100.0, {"role": "hero"})
    before = len(b._history["role"])
    b.record(1.0, {"role": "hero"})  # out-of-order
    assert len(b._history["role"]) == before + 1
    # Rueckfrage in der Vergangenheit bleibt exakt
    assert b.allow(2.0, {"role": "hero"})
