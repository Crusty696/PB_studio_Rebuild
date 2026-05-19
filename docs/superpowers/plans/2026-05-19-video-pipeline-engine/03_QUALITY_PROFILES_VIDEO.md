# 03 — Quality-Profiles Video

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 1
> Status: planned · 2026-05-19

## Profile

| Profil | Scene-Threshold | Keyframe-Sample | SigLIP-Resolution | RAFT-Resolution | VLM-Frequenz | Proxy-Bitrate |
|---|---|---|---|---|---|---|
| **Maximum Quality (Default)** | sensitiv | 1 Frame/2 s + alle Scene-Anchors | 384px native | 1080p native | jede Szene | 6 Mbps |
| **Balanced** | medium | 1 Frame/4 s | 384px | 720p downscale | jede 2. Szene | 3 Mbps |
| **Fast Preview** | grob | 1 Frame/8 s | 224px | 480p | jede 4. Szene | 1 Mbps |

## Default = Maximum Quality

User muss aktiv runterschalten. Pro Schritt ueberschreibbar (z. B. nur SigLIP Maximum, RAFT Balanced).

## Verifikation

- 4 h Video bei Maximum Quality auf GTX 1060: Schaetzung dokumentieren, Resume bei Crash funktioniert
- `pytest tests/test_services/test_video_quality_profiles.py -v` gruen
