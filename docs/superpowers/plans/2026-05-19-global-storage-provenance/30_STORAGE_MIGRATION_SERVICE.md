# 30 — Storage-Migration-Service

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3

## Ziel

Bestehende V2-Stems + Plan-A-Video-Outputs in `by_sha/`-Layout via Junction registrieren. Keine physische Verschiebung.

## Scope

- Service durchlaeuft V2-Stems-Tabellen, berechnet `source_sha256` pro Track.
- Legt `by_sha/<sha>/audio/` mit Junction zu `storage/stems/<track_id>/`.
- Analog Plan-A.
- Idempotent.
- Progress-Reporting.

## Out of Scope

- Loeschen alter Layouts — kommt erst nach User-Bestaetigung.

## Verifikation

- Migration-Lauf gegen Test-DB
- `pytest tests/test_services/test_storage_migration.py -v` gruen
