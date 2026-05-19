# 41 — Caller-Migration: Services

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

`services/video_analysis_service.py` und Konsumenten auf neuen Pipeline-Orchestrator umstellen.

## Reihenfolge

1. `services/video_analysis_service.py` deprecated markieren, Funktionen als Adapter auf `VideoAnalysisPipeline`.
2. Caller von `video_analysis_service` migriert.
3. Nach Plan-A Phase 42 fertig: `video_analysis_service` entfernt.

## Verifikation

- Pro Caller Service-Coverage-Tests (≥ 85 %)
