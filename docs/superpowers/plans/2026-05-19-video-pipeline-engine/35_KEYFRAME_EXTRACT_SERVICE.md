# 35 — Keyframe-Extract-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Stage-Wrapper um Keyframe-Selector (14) + Decoder (10).

## Scope

- Liest `scenes.json`.
- Pro Szene N Keyframes laut Quality-Profile.
- JPEG-Encode via PIL (Quality 95).
- Output: `keyframes/<scene_idx>_<role>.jpg`.
- Resume: skip bereits vorhandene Files.

## Verifikation

- Anzahl Keyframes = Szenen × N
- Bilder optisch korrekt (Manual-Spot-Check via Test-Datensatz)
- `pytest tests/test_services/test_keyframe_extract.py -v` gruen
