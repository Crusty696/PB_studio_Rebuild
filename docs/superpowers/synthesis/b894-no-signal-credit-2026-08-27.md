# B-894 No-Signal-Credit — 2026-08-27

Status: `code-fix-pending-live-verification`

## Root Cause

Reranker lieferte `no_signal_axes`, Pipeline persistierte jedoch nur
`brain_v3_scores`. Feedback credited dadurch neutrale/nicht-kausale Achsen.
Explizit leeres Mapping wurde zusaetzlich zu Legacy-Uniform kollabiert.

## Codefix

- Pipeline-Rationale traegt `brain_v3_no_signal_axes`.
- Gemeinsamer Parser entfernt diese Achsen fuer direktes Feedback und
  Timeline-Lernsync.
- `{}` bedeutet autoritativ All-No-Signal und schreibt 0 Buckets.
- `None` behaelt Legacy-Uniform-Verhalten.
- Kein DB-/Schemawechsel.

## Direkte Verifikation

- `py_compile`: PASS.
- B-894 Pipeline-/All-No-Signal-Vertrag: 2 PASS.
- Enge direkte/Legacy-Parservertraege: 3 PASS.
- Kein App-/Auto-Edit-Live; gesammelt am Fixwellenende.
