# 32 — Cross-Project-Reuse UX

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3

## Ziel

User importiert Datei in Projekt B die schon in Projekt A analysiert ist → Notify-Toast.

## Scope

- Beim Import: Lookup `analysis_jobs` mit `source_sha256`.
- Wenn Treffer:
  - Toast (non-modal): "Datei wurde bereits in Projekt <name> vollstaendig analysiert. Ergebnisse werden mitverwendet."
  - Status-Panel zeigt sofort gruene Schritte.
  - Tooltip pro Schritt: "Erzeugt am <datum> in Projekt <name>, Modell <X>".
- Manueller "Neu generieren"-Button bleibt pro Schritt verfuegbar.
- Setting: "Nicht mehr fragen" pro Projekt.

## Verifikation

- Re-Import → Toast erscheint
- Tooltip zeigt Provenance
- `pytest tests/test_ui/test_cross_project_reuse.py -v` gruen

## Implementation Status — 2026-06-15

Status: `code-complete-tests-green-live-pending`

- Implementiert: `services/storage_provenance/cross_project_reuse.py`.
- Import-Pfad schreibt wiederverwendbare Provenance-Hits in `analysis_status`.
- Status-Panel zeigt Provenance-Tooltips pro wiederverwendetem Step.
- Import-Controller zeigt nicht-modalen Hinweis plus projektbezogenes "Nicht mehr fragen".
- Tests: `tests/test_services/test_cross_project_reuse.py`, `tests/ui/test_cross_project_reuse.py`.
- Verifiziert: Cross-Project-Reuse Fokus `5 passed`; OTK-021 Slice `20 passed`; py_compile gruen; `git diff --check` gruen.
- Offen: realer GUI-Reimport in zwei Projekten und Tooltip-Klickpfad nicht live verifiziert. Kein `fixed`.
