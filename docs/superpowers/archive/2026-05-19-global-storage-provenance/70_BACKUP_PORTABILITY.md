# 70 — Backup + Portability

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Cross-Cutting

## Ziel

User kann gesamte Analyse-Datenbank + Storage backuppen ohne Daten-Verlust.

## Scope

- Backup-Manifest: DB-Schema-Version + Storage-Layout-Version + Modell-Versionen.
- User-Setting: "Backup-Verzeichnis" + Frequenz (manuell / daily / weekly).
- Backup-Inhalt: `database/pb_studio.db` + `storage/by_sha/` Junction-Targets (full-copy, nicht nur Junctions).
- Restore: Reverse-Operation. Junction wieder anlegen.

## Out of Scope

- Cloud-Backup.

## Verifikation

- Backup + Restore auf VM
- `pytest tests/test_services/test_backup.py -v` gruen
