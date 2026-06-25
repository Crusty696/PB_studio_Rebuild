# 75 — Uninstall

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

Sauberer App-Entfernung.

## Scope

- Uninstaller fragt:
  - "Modelle loeschen?" (sonst bleiben unter `%APPDATA%`, Default: nein wegen Datenverlust)
  - "Settings + DB loeschen?" (Default: nein)
  - "HF-Token aus Credential-Manager entfernen?" (Default: ja)
- Verbleibt nach Uninstall:
  - `%APPDATA%/PBStudio/` mit Modellen + DB (wenn nicht gewaehlt)
  - Sonst leer

## Verifikation

- Manueller Uninstall-Test
- Re-Install findet alte Modelle wieder (wenn behalten)
