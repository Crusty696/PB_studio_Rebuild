# 70 — Error-Surface + Recovery (Video)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Error-Mapping

| Typ | Recovery | UI |
|---|---|---|
| Decode-Fehler (unsupportet Codec) | Stage `failed`, klare Message | Modal |
| Corrupted Video | Skip mit Hinweis | Toast |
| OOM (GPU) | Stage `partial`, kleinere Aufloesung retry | Toast |
| OOM (RAM) | Chunk-Groesse halbieren + retry | transparent |
| Disk-Full | Block, Warnung | Modal |
| GPU-Lock-Busy | Warten oder `partial` | Status-Dot |
| NVENC nicht verfuegbar | Fallback `libx264` | Toast |
| Resume-Checkpoint corrupted | Komplett neu starten | Modal |
| FFmpeg crash | Subprozess-Restart + retry | transparent |

## Verifikation

- Inject Corrupted-Video → Stage failed, andere Files weiter
- Inject OOM → Auto-Downsize
- `pytest tests/test_services/test_video_errors.py -v` gruen
