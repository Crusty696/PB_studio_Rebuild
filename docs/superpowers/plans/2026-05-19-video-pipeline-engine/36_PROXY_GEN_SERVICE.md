# 36 — Proxy-Generation-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Stage-Wrapper um Proxy-Generator (15).

## Scope

- Erste Stage nach decode_probe (UI braucht Proxy fruh).
- Wenn Original < 1080p: kann Proxy skippen, Original direkt nutzen.
- Resume: wenn proxy.mp4 schon existiert + Stream-SHA gleich → skip.
- Progress-Reporting per Sekunde encoded.

## Verifikation

- Proxy in akzeptabler Zeit (1080p 1min → < 30s mit NVENC)
- UI kann Proxy laden + playen
- `pytest tests/test_services/test_proxy_gen_service.py -v` gruen
