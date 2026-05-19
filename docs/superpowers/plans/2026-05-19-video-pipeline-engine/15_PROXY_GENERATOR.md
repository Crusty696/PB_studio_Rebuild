# 15 — Proxy-Generator

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Niedrig aufgeloeste Proxy-Datei fuer fluessiges UI-Editing. Analyse bleibt auf Original.

## Scope

```python
def generate_proxy(src: Path, dst: Path, *, max_width: int = 960,
                   bitrate: str = "3M", codec: str = "h264_nvenc") -> Path:
    """
    FFmpeg: -i src -vf scale=-2:max_height -c:v h264_nvenc -b:v 3M dst
    NVENC auf GTX 1060 (Hartregel D-040).
    Audio copy oder transcoded je nach Quelle.
    """
```

- Pro Quality-Profile andere Bitrate (siehe `03_QUALITY_PROFILES_VIDEO.md`).
- Proxy in `storage/video_analysis/<track_id>/proxy.mp4`.
- UI/Timeline/Player nutzt Proxy. Pipeline-Stages nutzen Original.
- Proxy-Cache: wenn schon erzeugt + Original-Stream-SHA gleich → reuse.

## Verifikation

- Proxy < 1/4 Original-Groesse
- Playback in QMediaPlayer fluessig
- NVENC aktiv (GPU-Last)
- `pytest tests/test_services/test_proxy_gen.py -v` gruen
