# Skeptic log: b687-crossfade-av-sync (2026-07-24)

Read-only Audit. Nur _sandbox_meta/risks.md + skeptic_log.md geschrieben.

## Kommandos / Rohbelege

### Diff / Scope
- `git diff main..sandbox/b687-crossfade-av-sync --stat`
  -> services/export_service.py +65/-13, tests/test_b687_d1_av_length.py +101 (neu)
- Betroffene Funktion: _export_with_filtergraph (:873-1082). Concat/Pacing unberuehrt.

### Callsite-Grep
- `grep -rn "_export_with_filtergraph\b"`
  Prod: export_service.py:403 (export_timeline), :1572 (export_preview),
        :770 (batched-Rekursion)
  Tests: test_b332 (3x fake), test_b580 (2x fake), test_b687_d1 (:43),
         test_b687_xfade_offset_clamp (:40), test_cycle6 (inspect.getsource)
- Seg-Dict "duration": :347 `clip.duration or 10.0`, :1523 `clip.duration or 10.0`
  -> in beiden Prod-Buildern immer truthy.

### Test-Laeufe (conda env pb-studio, Python 3.10.20)
- pytest test_b687_xfade_offset_clamp + test_b687_d1_av_length +
  test_b332 + test_b580 + test_cycle6 -> 13 passed in 3.42s
- pytest test_a1_crossfades + test_b397_gap_validation + test_optb_default_hard_cuts
  -> 5 passed in 49.27s
- D2-Test (test_b687_xfade_offset_clamp) NICHT im Diff geaendert, trotzdem gruen.

### Arithmetik-Beweis (per Hand + Sim)
- Invariante: xfade_dur_i == ext[i-1] (bindender min-Term). ext in {0} u [0.1,2].
- eff_dur[i] = source_duration[i] + ext[i]; ext[last]=0.
- accumulated nach i = Sigma_{<=i} slot + ext[i]; final = Sigma slot = Audio.

### Edge-Case-Simulation (services.export_service, _run_ffmpeg gemockt)
- n==2 (dur2/dur2, xf1, cd60): -t=[3.0,2.0], xfade=(1.0,offset2.0), concat=0
  -> Composite=4=Sigma slot, offset=start[1]. OK
- n==2 no-tail (slot0.3 cd0.3): -t=[0.3,2.0], xfade=[], concat=1
  -> ext[0]=0 (avail=0), harter Schnitt, KEIN Over-Read (-t[0]=0.3<=cd0.3). OK
- 5 Segmente je 0.05s Luecke: offsets=[2,4,6,8] vs starts=[2.05,4.1,6.15,8.2]
  -> kumulierter Beat-Versatz 0.2s @ Segment5. P2-1 (gap-drift, pre-existing).
- "duration"-Key fehlt: -t=[3.0,2.0] (=src2+ext1 via avail=xf_next-Fallback)
  -> latenter Over-Read wenn echte Datei < 3.0s. P2-2. In Prod nicht erreichbar.

## Bewertung
- P0: 0, P1: 0, P2: 4 (gap-drift, over-read-fallback, >=0.1-Schwelle, preview-trim),
  P3: 3 Notizen.
- Hauptbedingung: echter ffmpeg-Live-Verify (AK1/AK4/AK5) steht aus, Mock ersetzt ihn nicht.
