# 71 — Observability (Video)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Scope

- Per-Stage Log: `ts, track_id, stage, duration_s, fps_processed, mb_in, mb_out, ok`
- Log in `video_pipeline_log` Tabelle + JSONL `logs/video_pipeline.jsonl`.
- Status-Panel zeigt heutige / Wochen-Statistik pro Stage.
- Debug-Toggle fuer verbose-Log.
- Log-Rotation 30 Tage.

## Verifikation

- Usage-Log fuellt sich
- Aggregate-Plot korrekt
- `pytest tests/test_services/test_video_observability.py -v` gruen
