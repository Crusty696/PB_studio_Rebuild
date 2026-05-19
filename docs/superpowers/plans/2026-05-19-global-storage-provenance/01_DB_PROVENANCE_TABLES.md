# 01 — DB-Provenance-Tabellen

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 1
> Status: planned · 2026-05-19

## Ziel

Zentrale Tabellen fuer "welcher Schritt fuer welche Datei mit welchem Modell + Parametern erledigt".

## Schema

```sql
CREATE TABLE analysis_jobs (
    id INTEGER PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    step_id TEXT NOT NULL,
    step_version TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    status TEXT NOT NULL,                  -- pending / running / done / failed / partial / stale
    produced_by_model TEXT,                -- z. B. "siglip-so400m"
    produced_by_model_version TEXT,
    coverage_percent REAL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    duration_seconds REAL,
    error TEXT,
    UNIQUE (source_sha256, step_id, step_version, params_hash)
);

CREATE TABLE analysis_artifacts (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,           -- "stem" / "json" / "image" / "npy"
    artifact_role TEXT NOT NULL,           -- "vocals_stem" / "scenes" / "embeddings"
    path TEXT NOT NULL,                    -- relativ zu storage/by_sha/<sha>/
    bytes INTEGER,
    sha256 TEXT
);

CREATE TABLE step_deps (
    step_id TEXT NOT NULL,
    depends_on_step_id TEXT NOT NULL,
    uses_artifact_role TEXT,
    PRIMARY KEY (step_id, depends_on_step_id)
);

CREATE TABLE project_sources (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    current_source_path TEXT NOT NULL,     -- letzter bekannter Pfad
    last_seen_at TIMESTAMP,
    UNIQUE (project_id, source_sha256)
);
```

## Migrations-Pflicht

- Idempotent (Vor-Check wie SCHNITT A1-A3)
- DB-Schema-Version-Bump

## Verifikation

- Migration laeuft idempotent
- `pytest tests/test_db/test_provenance_migration.py -v` gruen
