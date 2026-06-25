# 50 — Tier 4: Service-Coverage

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19`

## Scope

- `services/storage_provenance/*` ≥ 85 %
- Provenance-DB-Operationen
- Adapter-Layer
- File-Tracking-Repair
- Dedup-Lookup
- Storage-Migration

## Werkzeuge

- pytest-cov
- In-Memory-DB
- tmp_path Fixtures

## Verifikation

- Coverage-Report ≥ 85 %
