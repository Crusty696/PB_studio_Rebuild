# Risks: b707-crossfade-mixed-group

## Verdict
proceed-with-conditions — kein P0/P1. Root-Cause-korrekt, minimal, real bewiesen bei 30 fps. Auflagen: ein echter 24/60-fps-Mixed-Render + reine-cut-mit-Effekt-Regression (Byte/Dauer) im verify bestaetigen.

## P0 — blockers
- keine. (7 Kategorien geprueft, s.u.)

## P1 — silent regressions
- keine bestaetigt.

## P2 — quality / offene Verifikation
- **fps != 30 nur in Theorie belegt** — `services/export_service.py:1051,1073` — `settb=1/{fps}` mit fps in {24.0, 25.0, 60.0} ist NUR unit-string-getestet (Test nutzt fps=25 als int) und theoretisch begruendet, NICHT mit echtem ffmpeg gerendert. Real bewiesen ist ausschliesslich 30 fps (Gruppe 1 43.53 s, 94 Seg 338 s). Mechanismus haelt: fps-Filter setzt output tb = av_inv_q(framerate) = 1/fps (vf_fps.c), settb evaluiert `1/24.0` etc. via av_d2q -> exakte kleine Rationale 1/24, 1/25, 1/60 -> Match. Falls bei einem fps-Wert wider Erwarten kein Match: Mixed-Gruppe faellt im Batched-Pfad still auf Hard-Cut zurueck (Crossfades weg, kein Crash), im Nicht-Batched-Pfad (<=12 Seg) propagiert 0-Frames als RuntimeError bis zum Caller. Evidence: nur 30-fps-Lauf im plan/verify. Fix: EIN echter Mixed-Render bei 24 ODER 60 fps im verify (rc==0, >0 Frames, Crossfade sichtbar).
- **Reine-cut-mit-Effekt-Kette bekommt jetzt settb** — `services/export_service.py:1051,1073` + Branch `has_effects` `services/export_service.py:409-420`. Reine cut-Gruppe geht durch _export_optimized_concat (unberuehrt), ABER cut-only MIT brightness/contrast (has_effects=True, alle crossfade=0) laeuft durch _export_with_filtergraph -> Kette aus reinen concat-Knoten, die jetzt ALLE settb tragen. settb ist ein reines PTS-Relabel (av_rescale_q, kein Frame-Drop/Dup, Dauer erhalten), also erwartet neutral — aber es aendert einen bisher funktionierenden Pfad. Evidence: verify-plan listet cut-only-Regression, aber nur allgemeine cut-Gruppe; die has_effects-cut-Variante muss explizit mit rein. Fix: verify muss cut-only-MIT-Effekt (z.B. brightness!=0, alle crossfade=0) real rendern und Dauer==Baseline bestaetigen.

## P3 — notes
- **Float-Formatierung `1/30.0`** — `services/export_service.py:1051,1073` — Produktion uebergibt fps als float (Default 30.0), String wird `settb=1/30.0`. av_d2q(0.03333) liefert exakt 1/30 (kleine Denominatoren) -> haelt fuer ganzzahlige fps. Variant C (settb=AVTB uniform an allen Knoten) waere fps-Wert-robust; nur adoptieren, falls je fraktionaler Export-fps (29.97) eingefuehrt wird. Aktuell nicht der Fall (fps_combo 24/25/30/60, nicht editierbar).
- **Doppel-Rescale concat(1/1000000)->settb(1/fps)** — theoretisch weniger sauber als AVTB-uniform; av_rescale_q ist wall-clock-erhaltend, Dauer 43.5 s belegt keinen Drift. Vernachlaessigbar.
- **Unit-Test-Praezision** — `tests/test_services/test_b707_mixed_crossfade_group.py:58,85` — Regex `settb=1/30` matcht auch fehlerhaftes `1/300`/`1/30.0`; lockt weder Produktions-float `30.0` noch schliesst Ziffern-Anhang aus. Kosmetisch; Assertion-Logik (n_settb==n_concat) ist inhaltlich korrekt.
- Der Test deckt gut ab: concat VOR xfade UND concat NACH xfade (Muster cut,cut,xfade,cut) -> tb-Konsistenz ueber Knotengrenzen wird zumindest strukturell geprueft.

## Checked categories
- [x] Callsite coverage — _export_with_filtergraph 2 direkte Caller (`:415` has_effects, `:1605`) + rekursiv via _export_with_filtergraph_batched `:782`. Batched baut Kette NICHT selbst nach, ruft dieselbe Funktion -> Fix propagiert. Keine Signatur-Aenderung. Andere Tests: b332/b580 monkeypatchen die Funktion (neutral), b687_d1/b687_clamp/cycle6 asserten xfade-Offsets/AV-Laenge/script-Pfad — kein Assert auf concat-String -> brechen NICHT. 0 gebrochene Callsites.
- [x] Side effects (GPU/DB/Threads/IO) — keine. settb = reine Timestamp-Metadaten-Op, kein Decode/Encode, kein VRAM. _video_encode_args()/NVENC/hwaccel unberuehrt. Kein DB/Thread/Lock-Impact. filter_complex_script-Pfad (>50 Seg/>16000 chars) schreibt settb korrekt in utf-8-Datei; Komma = chain-interner Filter-Separator, kein Shell-Escaping (Datei), 94-Seg-Lauf ohne Fallback belegt.
- [x] Behavioral drift — settb rescaled PTS wall-clock-erhaltend (av_rescale_q in settb filter_frame), KEIN Frame-Drop/Dup, Dauer/Framerate unveraendert. Concern #1 entkraeftet. xfade-Output-tb = Input-tb (vf_xfade config_output kopiert time_base) = 1/fps -> nach settb ist die ganze Kette durchgaengig 1/fps; kein settb nach xfade noetig (Concern #3 geloest, empirisch durch funktionierende reine-xfade-Kette gestuetzt).
- [x] Migration / compat — keine Datenformate/DB/Config/API beruehrt. Nur Filtergraph-String.
- [x] Test gaps — Unit deckt gemischt + rein-cut + rein-xfade auf String-Ebene. Luecke: kein echter 24/60-fps-Render, kein echter cut-mit-Effekt-Regressionsrender (-> P2-Auflagen an verify).
- [x] Plan logical gaps — Plan praezise (exakte Alt/Neu-Strings, Zeilen). Annahme "fps immer ganzzahlig" explizit als offene Frage markiert. Reversibel (2 String-Suffixe, git checkout). Keine vagen Schritte.
- [x] PB-Studio-spezifisch — Pacing/Beat-Anker (offset==start[i]) unberuehrt; B-687 Overlap-Arithmetik (ext/eff_dur/accumulated_duration) bit-identisch, settb beruehrt nur concat-Zweig, nicht xfade-Zweig. Batched-Gruppengrenzen (concat-demux -c:v copy) unabhaengig von per-Gruppe-Filter-tb -> Concern #5 entkraeftet, 94-Seg-Lauf belegt. Kein Scope-Leak.

## Recommendations
1. Vor apply: verify MUSS zwei echte ffmpeg-Laeufe ergaenzen — (a) Mixed-Gruppe bei 24 ODER 60 fps (>0 Frames, Crossfade sichtbar), (b) cut-only MIT brightness/contrast (alle crossfade=0, has_effects-Pfad) Dauer==Baseline.
2. Falls je fraktionaler Export-fps geplant: auf Variant C (settb=AVTB uniform) wechseln — dann fps-Wert-robust.
3. Keine Code-Aenderung noetig; Fix ist apply-ready sobald die zwei verify-Laeufe gruen sind.
