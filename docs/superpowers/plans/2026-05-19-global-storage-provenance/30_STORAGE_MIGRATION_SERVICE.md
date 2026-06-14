# 30 — Storage-Migration-Service

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3
> Status: code-complete-tests-green · 2026-06-14

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

## Progress 2026-06-14

- Implementiert `services/storage_provenance/storage_migration.py`.
- V2-Stems: `source_sha256` strict berechnet, `project_sources` gesetzt, `analysis_jobs`/`analysis_artifacts` angelegt, `by_sha/.../audio/stems` als Junction/Symlink auf Legacy-Stems registriert.
- Plan-A-Video-Outputs: `proxy_path`, `embeddings_path`, `motion_path` als Provenance-Artefakte registriert.
- Idempotenz verifiziert: zweiter Lauf erzeugt keine doppelten `project_sources`/`analysis_jobs`.
- Layout-Fix: `relative_artifact_path()` folgt Junctions nicht mehr mit `resolve()`, damit DB-Pfade relativ zu `by_sha` bleiben.
- Verifiziert: `tests/test_services/test_storage_migration.py`; OTK-021 Service-Suite `18 passed`; py_compile gruen; `git diff --check` gruen.
- Kein Produkt-Live-Verify. Kein `fixed` Marker.
