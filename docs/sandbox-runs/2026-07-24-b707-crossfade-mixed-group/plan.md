# Implementation plan: b707-crossfade-mixed-group

## Pre-checks
- [ ] Worktree C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild_sandbox_b707-crossfade-mixed-group existiert, Branch sandbox/b707-crossfade-mixed-group, clean (nur _sandbox_meta/ untracked).
- [ ] Baseline: git show 8cb5786 + aktueller HEAD (49e987e) failen Gruppe 1 identisch (0 Frames) - schon belegt, in baseline/ festhalten.
- [ ] conda-Python C:/Users/David_Lochmann/miniconda3/envs/pb-studio/python.exe, ffmpeg/ffprobe auf PATH.

## Steps

1. **services/export_service.py::_export_with_filtergraph (Zeile 1045, erstes-Paar-concat)**
   - WAS: concat-Node um Timebase-Reset auf fps-tb ergaenzen.
   - Alt:  filter_parts.append("[v0][v1]concat=n=2:v=1:a=0[xf0]")
   - Neu:  filter_parts.append(f"[v0][v1]concat=n=2:v=1:a=0,settb=1/{fps}[xf0]")
   - WARUM: concat setzt Output-tb auf 1/1000000; settb=1/fps bringt sie zurueck auf die
     tb der fps-normalisierten [vi]-Streams, damit ein nachfolgender xfade beide Inputs mit
     gleicher Timebase sieht (Root-Cause). Kein Frame-Verlust (settb reskaliert nur PTS-Label).

2. **services/export_service.py::_export_with_filtergraph (Zeile 1063-1065, Loop-concat)**
   - WAS: identischer settb-Suffix am Loop-concat-Node.
   - Alt:  filter_parts.append(f"[{current_label}][v{i}]concat=n=2:v=1:a=0[xf{i-1}]")
   - Neu:  filter_parts.append(f"[{current_label}][v{i}]concat=n=2:v=1:a=0,settb=1/{fps}[xf{i-1}]")
   - WARUM: deckt jeden concat-Uebergang in der Kette ab (auch cut-Runs zwischen xfade-Runs
     und nach einem xfade-Run). xfade-Node-Zeilen (1040/1057) bleiben UNVERAENDERT.

   Hinweis: Batched-Pfad (_export_with_filtergraph_batched, Zeile 782) und Single-Segment/
   reine-xfade-Pfade brauchen KEINE eigene Aenderung - sie rufen dieselbe Single-Chain bzw.
   enthalten keine concat-Knoten. Nur diese 2 Sites aendern.

3. **Test-Fixture (neu): tests/test_services/test_b707_mixed_crossfade_group.py**
   - Unit A (cmd-Konstruktion, kein ffmpeg): _export_with_filtergraph mit gemockter
     _run_ffmpeg; Assert: jeder ",settb=1/{fps}" folgt genau jedem "concat=n=2:v=1:a=0";
     Assert: xfade-Nodes enthalten KEIN settb; Assert: reine-xfade-Eingabe erzeugt 0 concat/
     0 settb (Pfad unberuehrt).
   - Test to add: tests/test_services/test_b707_mixed_crossfade_group.py::test_concat_nodes_get_settb
   - Test to add: ...::test_pure_xfade_chain_has_no_settb
   - Test to add: ...::test_pure_cut_chain_all_concat_get_settb

## Test plan
- Unit (cmd): siehe Step 3 - Filtergraph-String-Assertions ueber gemocktes _run_ffmpeg.
- Integration (ECHTES ffmpeg, app94_segs.json):
  - Gruppe 1 (Segmente 12-23, Muster [0,0,0,0,1,1,1,0,0,0,0,0]): rc==0, ffprobe-Dauer
    43.0-44.0 s (Sigma slot 43.184). ERWARTUNG belegt: 43.500 s.
  - Ganze 94 Segmente ueber export-Pfad (Batched, >12): rc==0, ffprobe-Dauer ~ Sigma(slot)
    aller 94, kein 0-Frames, kein Fallback-Warn "B-603: Batch-xfade-Pfad fehlgeschlagen" im Log.
- Regression (ECHTES ffmpeg):
  - cut-only-Gruppe (alle crossfade=0, 12 Segmente): rc==0, Dauer ~ Sigma(slot).
  - xfade-only-Gruppe (alle crossfade>0, 12 Segmente): rc==0, Dauer ~ Sigma(slot), Crossfades
    sichtbar; Ergebnis identisch zu vor dem Fix (kein settb an xfade-Nodes -> Bit-Diff nur an
    concat-losen Ketten = keiner).
- Live verify: verify_log.md je Kriterium gruen/rot mit ffprobe-Zahlen + ffmpeg-rc.
- Batch-Regeln beachten: die 3 Unit-Tests + Integrationslaeufe in EINEM Testlauf buendeln,
  nicht pro Schritt einzeln (User-Regel batch-tests).

## Rollback
- Worktree-Branch verwerfen - kein main-Impact. Fix ist 2 String-Suffixe; git checkout --
  services/export_service.py stellt Ausgangszustand her.

## Done definition
- Alle Acceptance-Kriterien in verify_log.md gruen (Gruppe 1 + 94 Segmente + beide Regressionen).
- Skeptic-Risiken <= P2 (insb. reine-cut-Regression, fraktionaler-fps-Rand bestaetigt/entschaerft).
- Kein "still 0 Frames -> Hard-Cut"-Fallback mehr im gemischten Fall.
