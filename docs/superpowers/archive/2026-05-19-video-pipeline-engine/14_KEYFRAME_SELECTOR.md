# 14 — Keyframe-Selector

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Pro Szene N repraesentative Frames waehlen + extrahieren.

## Strategien

| Modus | Frames pro Szene | Anwendung |
|---|---|---|
| `mid` | 1 (Mitte) | Fast |
| `anchors_3` | 3 (Anfang/Mitte/Ende) | Default Maximum |
| `i_frames` | nur native I-Frames | sehr fast |

## Output

- JPEG-Datei pro Keyframe in `storage/video_analysis/<track_id>/keyframes/<scene_idx>_<role>.jpg`
- Metadata: time_s, scene_idx, role

## Verifikation

- Anzahl Keyframes = Szenen × N
- Zeitstempel ±1 Frame korrekt
- `pytest tests/test_services/test_keyframe_selector.py -v` gruen
