# Skeptic-Log: b707-crossfade-mixed-group (2026-07-24)

## Commands
- `git log --oneline -8` -> HEAD 75302e8 sandbox(B-707) settb-Fix.
- `git diff main..sandbox/b707-crossfade-mixed-group --stat` -> nur services/export_service.py (+13/-2) + neuer Test (+87).
- `git diff ... -- services/export_service.py` -> genau 2 Sites geaendert: `:1051` erstes-Paar-concat, `:1073` Loop-concat. Alt `...a=0[xf..]` -> Neu `...a=0,settb=1/{fps}[xf..]`. xfade-Knoten `:1040-1042` / `:1063-1066` UNVERAENDERT.

## Reads
- export_service.py:885-1143 _export_with_filtergraph (voll). :906-923 Batch-Delegation + hard-cut-Fallback via _export_optimized_concat. :1114-1124 _run_ffmpeg in try/FINALLY (kein except -> 0-Frames propagiert im Nicht-Batched-Pfad).
- export_service.py:718-882 _export_with_filtergraph_batched -> :782 ruft _export_with_filtergraph pro Gruppe (baut Kette NICHT selbst) -> Fix propagiert. :839 concat-demux -c:v copy ueber Gruppen (Stream-Copy, unabhaengig von Filter-tb).
- export_service.py:251 fps: float=30.0. :409-420 Branch: has_effects (crossfade>0 OR brightness!=0 OR contrast!=1) -> _export_with_filtergraph; sonst _export_optimized_concat.
- test_b707_mixed_crossfade_group.py voll: 3 Tests (mixed cut,cut,xfade,cut fps=30; pure-xfade fps=30; pure-cut fps=25). Mocked _run_ffmpeg/_prepare_normalized_audio.

## Greps
- `concat=n=2:v=1:a=0|_export_with_filtergraph|settb` in tests/ -> b332/b580 monkeypatchen die Funktion (neutral); b687_d1/b687_clamp asserten offsets/AV-Laenge (kein concat-String-Assert); cycle6 inspect.getsource fuer script-Pfad. Keiner bricht durch settb.
- b687_d1:76/82/99/101 + b687_clamp:56/60/64/78 -> Assertions nur auf xfade dur/offset & composite length. settb beruehrt weder xfade-Zweig noch accumulated_duration -> gruen.

## ffmpeg-Internals (Begruendung, nicht ausgefuehrt)
- vf_fps.c config_output: outlink->time_base = av_inv_q(framerate) = 1/fps exakt.
- settb filter_frame: frame->pts = av_rescale_q(pts, intb, outtb) -> wall-clock-erhaltend, kein Frame-Drop/Dup.
- settb config: expr -> double -> av_d2q(res, INT_MAX). 1/30.0,1/24.0,1/25.0,1/60.0 -> kleine exakte Rationale.
- vf_xfade.c config_output: outlink->time_base = inlink0->time_base -> xfade erhaelt 1/fps -> Kette durchgaengig konsistent, kein settb nach xfade noetig.

## Empirie (aus plan.md/analysis.md, nicht selbst reproduziert)
- 30 fps: Gruppe 1 43.53 s (Sigma 43.18), 94 Seg 338.2 s, kein Fallback-Warn. Nur 30 fps belegt.
- 24/25/60 fps: NICHT real gerendert -> P2.

## Findings
P0=0, P1=0, P2=2 (24/60-fps real; cut-mit-Effekt-Regression), P3=3 (float-fmt/Variant-C, Doppel-Rescale, Test-Regex-Praezision).
