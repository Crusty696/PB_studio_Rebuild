# 39 — Cross-Modal AV-Alignment

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Video-Stages + Audio-V2-Outputs zusammenfuehren. Cut-Vorschlaege, Pacing-Plan, Drop-trifft-Visual-Match.

## Scope

```python
class CrossModalAvAlignmentService:
    def align(self, video_track_id, audio_track_id) -> AlignmentResult:
        # Liest V2-Outputs: beats.json, sections.json, drops.json, energy.json
        # Liest Video-Outputs: scenes.json, motion.json, captions.json
        # Generiert: cut_plan.json
        ...
```

- Liest V2-Daten **read-only** (keine V2-Modifikation).
- Reasoner-Aufruf (Plan B `reasoning_heavy` Rolle):
  - Input: AV-Map + Captions + Beats
  - Output: Cut-Plan + Begruendung
- Falls Plan B Reasoner nicht ready: heuristischer Fallback (Beats × Scene-Boundaries-Match).

## Output

- `storage/video_analysis/<track_id>/cross_modal/cut_plan.json`
- `storage/video_analysis/<track_id>/cross_modal/pacing_plan.json`

## Verifikation

- Mit V2-Mock-Daten + Video-Mock: plausible Cut-Vorschlaege
- `pytest tests/test_services/test_cross_modal.py -v` gruen
