# 23 — Modell-Storage-Management

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Disk-Verbrauch kontrolliert. Modelle umziehbar. Cleanup-Funktion.

## Scope

- Default-Pfad: `%APPDATA%/PBStudio/llm/ollama/`
- User-Override per Settings: anderer Drive (z. B. D:\PBStudio-Models).
- Disk-Space-Probe (`shutil.disk_usage`) vor Download. Wenn < required + 2 GB Reserve → Block + User-Warnung.
- Modell-Liste-UI zeigt:
  - belegter Speicher pro Modell
  - last_used_at
  - Delete-Button
- Cleanup-Tool: "Modelle die letzten N Tagen nicht genutzt" auswaehlbar loeschen.
- Migration: User aendert Storage-Pfad → Files kopieren + alte loeschen + Daemon-Env updaten.

## Out of Scope

- Backup-Strategie (Modelle sind regenerierbar, nicht backup-pflichtig).

## Verifikation

- Move zwischen Drives funktioniert ohne Modell-Pfad-Bruch
- Disk-Full-Simulation → klare Fehlermeldung statt Crash
- `pytest tests/test_services/test_llm_storage.py -v` gruen
