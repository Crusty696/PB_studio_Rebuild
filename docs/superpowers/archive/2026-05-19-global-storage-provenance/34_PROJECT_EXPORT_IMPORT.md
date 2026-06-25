# 34 — Project-Export + Import

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3

## Ziel

User kann Projekt + Analyse-Artefakte als Bundle exportieren / importieren.

## Scope

- Export: zip-Bundle `<project>.pbbundle`:
  - Projekt-DB-Subset (nur dieses Projekt)
  - `by_sha/<sha>/` Verzeichnisse aller im Projekt referenzierten Quellen
  - Manifest (Versionen / SHAs)
- Import:
  - Manifest pruefen
  - SHA-Verify pro Datei
  - Bei Konflikt (SHA bereits da): existierende Artefakte behalten
  - Projekt anlegen + Sources verlinken

## Out of Scope

- Cloud-Sync.

## Verifikation

- Export + Import auf demselben Rechner
- Export + Import auf anderem Rechner
- `pytest tests/test_services/test_project_export.py -v` gruen

## Implementation Status — 2026-06-15

Status: `code-complete-tests-green-live-pending`

- Implementiert: `services/storage_provenance/project_bundle.py`.
- Export: `.pbbundle` ZIP mit `manifest.json`, Project-Subset, `project_sources`, `analysis_jobs`, `analysis_artifacts`, referenzierten `storage/by_sha/...` Dateien.
- Import: Manifest-Version pruefen, Storage-Datei-SHA pruefen, Projekt anlegen, Sources verlinken, Jobs/Artifacts upserten, bestehende Storage-Dateien bei Konflikt behalten.
- Tests: `tests/test_services/test_project_export.py`.
- Verifiziert: Project-Export Fokus `3 passed`; OTK-021 Slice `30 passed`; py_compile gruen; `git diff --check` gruen.
- Offen: Export+Import gleicher Rechner und anderer Rechner nicht live verifiziert. Kein `fixed`.
