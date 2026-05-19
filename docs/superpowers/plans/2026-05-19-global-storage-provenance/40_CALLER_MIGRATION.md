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
