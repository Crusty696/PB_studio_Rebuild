# B-888 Kanonischer Tie-Break — 2026-08-27

Status: `code-fix-pending-live-verification`

## Root Cause

Mehrere Kandidatensorts verwendeten nur Score. Gleiche Werte erbten damit
DB-, VectorDB- oder Caller-Reihenfolge. VectorDB nutzte unstabiles
`argpartition` ohne kanonische SQL-Reihenfolge.

## Codefix

- Persistente Clip-/Video-/Scene-ID als aufsteigender Tie-Key.
- `available_ids` kanonisch sortiert.
- VectorDB `ORDER BY id ASC` und stable Similarity-Sort.
- Scoreformeln, Seed und Sampling unveraendert.

## Direkte Verifikation

- `py_compile`: PASS.
- Umgekehrte Pipeline-Kandidatenreihenfolge: gleiche Wahl.
- Identische Vector-Similarities: Composite-IDs aufsteigend.
- Ergebnis: `2 passed`.
- Echter Projekt-/Timeline-Livepfad offen; folgt gesammelt.
