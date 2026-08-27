# B-909 — Golden-Baseline roter_faden

Status: `code-fix-pending-full-suite`

## Root Cause

Baseline wurde zuletzt mit `c9786d3` am 2026-07-15 aktualisiert. B-842/
`fd3782e` fuehrte am 2026-08-15 absichtlich `roter_faden_contrib` samt
persistiertem Key ein, ohne Baseline nachzuziehen.

## Fix

Vorgesehener Generator mit `--overwrite`. Exakt zehn Einfuegungen
`"roter_faden": 0.0`; keine anderen Golden-Werte und kein Produktcode geaendert.

## Verifikation

- Gesamtlauf RED bis Stop: `1 failed, 294 passed, 271 subtests passed`.
- `git diff --check` PASS.
- Golden-Snapshot-Datei: `10 passed in 0.96s`.
- Voller Gesamtlauf pending.
