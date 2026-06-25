# 17 — Resume-Checkpoint

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Bei Crash / Cancel: naechster Lauf macht weiter ab letztem Chunk.

## Scope

- JSON-Datei `storage/video_analysis/<track_id>/checkpoint.json`:
  ```json
  {
    "plan_id": "VIDEO-PIPELINE-ENGINE-2026-05-19",
    "track_id": 42,
    "stream_sha256": "...",
    "stages": {
      "scene_detect":      {"status": "done",    "duration_s": 12.3},
      "keyframe_extract":  {"status": "running", "completed_scenes": 18, "total_scenes": 134},
      "siglip_embed":      {"status": "pending"},
      "raft_motion":       {"status": "pending"},
      "vlm_caption":       {"status": "pending"}
    },
    "last_update": "2026-05-19T00:00:00"
  }
  ```
- Atomic-Write (tmp + rename).
- Stages markieren ihren Fortschritt nach Sub-Chunk.
- Orchestrator liest Checkpoint beim Start → skip done-stages.

## Verifikation

- Kill mid-Stage → Resume-Lauf startet bei letztem Sub-Chunk
- Checkpoint nie korrupt (atomic-write)
- `pytest tests/test_services/test_resume_checkpoint.py -v` gruen
