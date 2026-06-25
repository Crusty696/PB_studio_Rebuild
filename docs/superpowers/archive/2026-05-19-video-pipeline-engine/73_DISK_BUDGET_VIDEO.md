# 73 — Disk-Budget Video

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Scope

- Disk-Space-Probe vor jeder Stage (`shutil.disk_usage`).
- Schwelle: < 2 GB frei → Block + Warnung.
- Pro Stage Disk-Bedarf-Schaetzung:
  - Proxy 4 h: ~3-6 GB
  - Keyframes 4 h: ~360 MB
  - SigLIP-Embeds: ~16 MB
  - Motion-JSON: ~5 MB
  - Captions-JSON: ~100 KB
- Cleanup-Tool:
  - "Letzten N Tage nicht genutzt" loeschen
  - Pro Track: Proxy / Embeds / Captions getrennt loeschbar (Re-Generate bei Bedarf)

## Verifikation

- Disk-Full-Simulation → klare Fehlermeldung
- `pytest tests/test_services/test_video_disk.py -v` gruen
