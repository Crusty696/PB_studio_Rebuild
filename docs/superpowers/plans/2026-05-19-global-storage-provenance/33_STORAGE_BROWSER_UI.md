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

## Implementation Status — 2026-06-15

Status: `code-complete-tests-green-live-pending`

- Implementiert: `services/storage_provenance/storage_browser.py`.
- Implementiert: `ui/dialogs/storage_browser_dialog.py`.
- Settings-Dialog oeffnet Storage-Browser.
- Tabelle: SHA kurz, Datei, Projekte, Stages, Bytes, Last Used, Aktion.
- Filter: nicht-genutzt in Projekten, alt > N Tage.
- Delete: pro Zeile und Bulk nur nach Confirm.
- Tests: `tests/test_services/test_storage_browser.py`, `tests/test_ui/test_storage_browser.py`.
- Verifiziert: Storage-Browser Fokus `5 passed`; OTK-021 Slice `27 passed`; py_compile gruen; `git diff --check` gruen.
- Offen: Settings-GUI-Klick, reale Tabelle und Delete-Confirm nicht live verifiziert. Kein `fixed`.
