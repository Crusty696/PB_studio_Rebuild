# 71 — Disk-Budget Global

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Cross-Cutting

## Ziel

User sieht globalen Disk-Verbrauch + Cleanup-Tools.

## Scope

- Storage-Browser zeigt: total / pro source_sha / pro Projekt.
- Auto-Cleanup-Setting:
  - Nicht-genutzte Artefakte (kein Project-Reference) automatisch loeschen nach N Tagen.
  - User-Confirm pro Bulk-Delete.
- Disk-Probe vor Migration → blockiert wenn zu wenig.

## Verifikation

- Cleanup-Schaetzung korrekt
- `pytest tests/test_services/test_disk_budget_global.py -v` gruen
