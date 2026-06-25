# 40 — Caller-Migration (V2 + Plan A + SCHNITT)

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19`

## Ziel

Bestehende Pipeline-Caller schreiben Provenance-Jobs in neue DB-Tabellen, ohne Storage zu verschieben.

## Reihenfolge

1. V2-Audio-Pipeline-Stages: vor/nach Stage-Run → `analysis_jobs`-Eintrag.
2. Plan-A-Video-Pipeline-Stages: dito.
3. SCHNITT-Audio-Subtab + Stem-Player: ueber Adapter-Layer (kein Direkt-Aufruf).
4. Brain V3: bleibt isoliert.
5. Plan B LLM: nutzt **eigene** `llm_*`-Tabellen, kein Provenance-Crosswalk.

## TDD-Pro-Caller

- RED: Test gegen Mock-Provenance-DB
- GREEN: Caller schreibt + liest
- REFACTOR: Adapter-Layer falls aelterer Pfad noch existiert

## Verifikation

- V2-Stage-Lauf legt Eintrag in `analysis_jobs` + `analysis_artifacts`
- Dedup-Hit bei Re-Run
- `pytest tests/test_services/test_caller_migration_storage.py -v` gruen

## Implementation Status — 2026-06-15

- `services/storage_provenance/caller_migration.py` added.
- Audio V2 `StemGenStage` records generated and reused stem artifacts into `analysis_jobs` and `analysis_artifacts`.
- Plan-A `VideoAnalysisPipeline` records done-stage artifacts into `analysis_jobs` and `analysis_artifacts`.
- SCHNITT stem access remains through existing adapter layer; no direct SCHNITT caller added.
- Brain V3 and Plan B LLM left isolated per plan.
- Verification: caller-migration focus `3 passed`; OTK-021 Slice `33 passed`; py_compile green.
- Product live verification pending; no `fixed` marker.
