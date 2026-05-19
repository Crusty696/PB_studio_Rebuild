# 33 — Storage-Browser-UI

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3

## Ziel

User sieht alle analysierten Dateien projekt-uebergreifend + kann gezielt loeschen.

## Scope

- Settings → "Storage-Browser":
  - Tabelle: source_sha (kurz) / file-name / projects-used-by / stages-done / total-bytes / last-used
  - Filter: nicht-genutzt-in-Projekten, alt > N Tage
  - Pro Zeile: "Analysen loeschen" (mit Confirm)
  - Bulk-Delete

## Verifikation

- Liste komplett + sortiert
- Bulk-Delete entfernt nur ausgewaehlte
- `pytest tests/test_ui/test_storage_browser.py -v` gruen
