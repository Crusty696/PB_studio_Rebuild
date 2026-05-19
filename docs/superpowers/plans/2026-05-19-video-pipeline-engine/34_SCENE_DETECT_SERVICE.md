# 34 — Scene-Detect-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Stage-Wrapper um Scene-Detect-Primitive (siehe 13).

## Scope

- Liest Quality-Profile-Threshold.
- Nutzt Proxy wenn vorhanden (Speed) — Cuts identisch zu Original.
- Output: `scenes.json` mit `[{idx, start_s, end_s, duration_s}]`.
- Coverage-Guard pruefen.

## Verifikation

- Solo_Natur bekannte Cuts
- `pytest tests/test_services/test_scene_detect_service.py -v` gruen
