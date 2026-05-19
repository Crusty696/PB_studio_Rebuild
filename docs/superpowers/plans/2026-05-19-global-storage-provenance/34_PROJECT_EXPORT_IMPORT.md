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
