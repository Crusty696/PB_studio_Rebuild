# 11 — File-Tracking + Repair

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 2

## Ziel

Source-Datei verschoben → App findet wieder via SHA + repariert `current_source_path`.

## Scope

- Beim App-Start oder Projekt-Open:
  - Scan `project_sources.current_source_path` → existiert? wenn nein → suchen.
  - Library-Scan in bekannten Verzeichnissen (User-Setting).
  - Match via `source_sha256`.
  - DB-Update `current_source_path`.
- Bei nicht-gefunden: User-Dialog "Datei <X> nicht gefunden — manuell suchen oder ignorieren?"

## Verifikation

- Datei verschoben + App-Restart → Pfad-Update
- `pytest tests/test_services/test_file_tracking.py -v` gruen
