# B-911 — Pacing-Scorer-Vertragsmenge

Status: code-fix-pending-live-verification

## Befund

Vierter Gesamttest stoppte bei 8 Prozent nach `385 passed`: `score()` lieferte
den seit B-842 produktiven Contribution-Key `roter_faden`, aber
`CANONICAL_TERM_KEYS` im selben Modul enthielt nur die vorherigen 15 Keys.

## Root Cause

Commit `fd3782e` ergaenzte Gewicht, Berechnung, Summe und Output, nicht jedoch
die kanonische Vertragsmenge. Zwei Termzahl-Kommentare blieben ebenfalls alt.

## Fix

- `roter_faden` in `CANONICAL_TERM_KEYS`
- Termzahl-Kommentare auf 16
- keine Berechnung, Gewichtung oder Kandidatenauswahl geaendert

## Verifikation

`pytest -q tests/pacing/test_pacing_scorer.py::test_term_contributions_sum_to_total_score`

Ergebnis: `1 passed in 0.97s`.

Vollsuite und echter Auto-Edit-/Timeline-Livepfad fehlen. Deshalb nicht
`fixed`.
