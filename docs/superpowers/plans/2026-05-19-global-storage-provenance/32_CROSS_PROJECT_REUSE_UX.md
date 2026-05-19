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
