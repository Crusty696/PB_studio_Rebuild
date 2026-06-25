# 50 — Tier 4: Service-Coverage-Tests (≥ 85 %)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: planned · 2026-05-19

## Scope

- `services/video_pipeline/orchestrator.py`
- `services/video_pipeline/stages/*`
- `services/video_pipeline/primitives/*`
- `services/video_pipeline/storage.py`

## Werkzeuge

- pytest-cov + Schwelle pro Modul
- Mock-Decoder (Phase 60)
- In-Memory-DB (StaticPool)

## Verifikation

- ≥ 85 % pro Service
