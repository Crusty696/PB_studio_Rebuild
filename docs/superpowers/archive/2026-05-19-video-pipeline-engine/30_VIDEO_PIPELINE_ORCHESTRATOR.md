# 30 — Video-Pipeline-Orchestrator

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3 Workspace+Services
> Status: planned · 2026-05-19

## Ziel

Analog Audio-V2 `AudioAnalysisPipeline`: QObject mit Stages + Signals + Resume.

## Scope

```python
class VideoAnalysisPipeline(QObject):
    stage_started  = Signal(str, str)             # (track_id, stage_id)
    stage_progress = Signal(str, str, int)        # (track_id, stage_id, percent)
    stage_done     = Signal(str, str)
    stage_failed   = Signal(str, str, str)        # (track_id, stage_id, error)
    pipeline_done  = Signal(str)
    
    def __init__(self, track_id, source_path, quality_profile, checkpoint_dir, ...): ...
    def run(self) -> None: ...                    # blocking; aufgerufen aus QThread
    def cancel(self) -> None: ...
```

## Stages (in DAG-Reihenfolge)

1. `decode_probe` — VideoMeta + stream_sha256
2. `proxy_gen`    — sofort UI-Editing
3. `scene_detect`
4. `keyframe_extract`
5. `siglip_embed`  (GPU-Lock-Aware)
6. `raft_motion`   (GPU-Lock-Aware)
7. `vlm_caption`   (Hook -> Plan B Backend, oder Stub-Mode)
8. `cross_modal`   (wenn V2-Audio fertig)

## Concurrency

- Pro Track ein Orchestrator-QThread (User-Mode B+C — manuell pro Schritt oder seriell alles).
- Globaler GPU-Lock-Awareness verhindert Doppel-GPU.

## Verifikation

- Solo_Natur-Clip durch alle Stages
- Resume nach Cancel
- `pytest tests/test_services/test_video_orchestrator.py -v` gruen
