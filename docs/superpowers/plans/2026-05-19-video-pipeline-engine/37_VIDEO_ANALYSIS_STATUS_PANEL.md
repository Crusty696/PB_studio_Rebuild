# 37 — Video-Analyse-Status-Panel

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

UI-Komponente die pro Video-Datei zeigt:
- welche Stages erledigt / laufend / fehlend
- pro Stage Modell-Provenance (`produced_by_model` wenn relevant)
- Re-Run-Button pro Stage
- "Alle ausstehenden starten" sequentiell

## Skizze

```
File: 2024-12-31_Live_Set.mp4   [Video-Analyse-Status]
──────────────────────────────────────────────────────────
 ✓ Decode-Probe       OK     duration 14m 03s
 ✓ Proxy              OK     proxy.mp4  423 MB
 ✓ Scene-Detect       102 Szenen
 ⟳ Keyframe-Extract   43/102 Szenen (42 %)
 · SigLIP-Embed       pending
 · RAFT-Motion        pending
 · VLM-Caption        pending     (Modell aus Plan B)
 · Cross-Modal-Sync   pending     (wartet auf V2-Audio-Outputs)

 [Alle ausstehenden Schritte starten]   [Pause]   [Cancel]
```

## Verifikation

- Live-Updates ueber Pipeline-Signals
- Manueller Re-Run-Button pro Stage
- `pytest tests/test_ui/test_video_status_panel.py -v` gruen
