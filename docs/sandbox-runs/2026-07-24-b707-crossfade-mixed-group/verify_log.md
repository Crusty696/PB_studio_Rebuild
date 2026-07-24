# Verify-Log — B-707 / Variant A (settb=1/{fps} an concat-Knoten)

Durchgefuehrt vom Haupt-Agent (echtes ffmpeg + Unit). Stand: 2026-07-24.

## AK1 — gemischte cut+crossfade-Gruppe rendert (vorher 0-Frames)
Gruppe 1 der echten app94_segs.json (Segmente 12-23, crossfade-Muster
[0,0,0,0,1,1,1,0,0,0,0,0]) via `_export_with_filtergraph`, echtes ffmpeg:
- Baseline (main/8cb5786): 0 Frames, "timebase do not match" -> Conversion failed.
- Fix: **rc==0, ffprobe dur=43.533s** (Sigma slot 43.184). Crossfades rendern. AK1 erfuellt.

## AK2 — voller realer 94-Segment-Export (Batched, >12 Segmente)
`_export_with_filtergraph_batched` mit allen 94 echten Segmenten:
- **rc==0, ffprobe dur=338.200s** (Sigma slot 337.14). Kein 0-Frames, kein
  "B-603: Batch-xfade-Pfad fehlgeschlagen"-Fallback mehr. (Im App-Export mit
  Audio + -shortest wird auf die Audiodauer 337.1s getrimmt -> A/V-synchron.)
  AK2 erfuellt.

## AK3 — Regression cut-only / xfade-only unveraendert
12-Segment-Testclips (testsrc), Slot je 2.0s -> Sigma slot 24.0s:
- cut_only (alle crossfade=0):  rc==0, dur=24.000s.
- xfade_only (alle crossfade>0): rc==0, dur=24.000s.
Beide korrekt; xfade-Knoten bekommen kein settb -> reine-xfade-Kette bit-identisch.

## AK4 — Unit (cmd-Konstruktion)
`tests/test_services/test_b707_mixed_crossfade_group.py`: 3 passed.
- concat-Knoten bekommen ,settb=1/{fps}; xfade-Knoten NICHT; reine-xfade-Kette 0 concat/0 settb.

## AK5 — Skeptiker-P2-Bedingungen (echtes ffmpeg, nachgereicht)
- (P2a) Mixed cut+xfade bei 60 fps: rc==0, dur=16.000s (Sigma slot 16.0). Fix wirkt fps-unabhaengig.
- (P2b) cut-only MIT brightness/contrast (has_effects-Pfad): rc==0, dur=12.000s (Sigma slot 12.0).
  Kein Dauer-/Frame-Regress durch settb an cut-Knoten.

## Verdikt
AK1-AK5 gruen (echtes ffmpeg + Unit). Skeptiker: 0 P0/P1, 2 P2 (beide durch AK5 geschlossen).
Apply-ready vorbehaltlich voller Suite auf main nach Apply. status: fixed nur User.
