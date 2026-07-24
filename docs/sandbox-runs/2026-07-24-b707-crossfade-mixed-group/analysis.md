# Analysis: b707-crossfade-mixed-group

## Goal
Gemischte cut+crossfade-Batch-Gruppe (crossfade_duration=0 UND >0 gemischt) soll im
Crossfade-Export ein valides Video MIT Crossfades an den richtigen Stellen rendern, statt
0 Frames zu liefern und still auf Hard-Cut-Concat zurueckzufallen. B-687-Overlap-Logik
bleibt erhalten; reine cut- und reine xfade-Gruppen bleiben unveraendert.

## Acceptance criteria
- [ ] Gemischte Gruppe (Muster [0,0,0,0,1,1,1,0,0,0,0,0]) rendert valides Video, >0 Frames.
- [ ] Crossfades sitzen an den richtigen Uebergaengen (offset == Beat-Grenze), Cuts dazwischen.
- [ ] ffprobe Video-Dauer ~ Sigma(slot) (~Audiodauer), kein A/V-Drift.
- [ ] B-687-Overlap-Extension (ext/eff_dur, offset=start[i]) greift weiter wo Crossfades rendern.
- [ ] Reine cut-Gruppen unveraendert funktionsfaehig.
- [ ] Reine xfade-Gruppen unveraendert funktionsfaehig.
- [ ] Batched-Pfad (>12 Segmente) und ganze 94 Segmente rendern durch.

## Current state

### Betroffene Codestelle
services/export_service.py::_export_with_filtergraph (~Zeile 885-1133). Baut EINE
Filterkette: pro Segment [i:v]scale...,setsar=1,fps={fps}[vi] (Zeile 1004-1014),
dann sequentiell pro Uebergang ENTWEDER xfade (Zeile 1040-1042 / 1057-1060) ODER
concat (Zeile 1045 / 1063-1065), je nach crossfade-Wert und B-687-Clamps.

Aufrufkette:
- _export_with_filtergraph_batched (Zeile 718) splittet >12 Segmente in Gruppen <=12,
  ruft je Gruppe _export_with_filtergraph (Zeile 782) -> dieselbe Single-Chain-Logik,
  danach concat-Demux ueber Gruppengrenzen (harte Schnitte, B-603). Der Fehler liegt
  IN der Einzelgruppe, nicht in der Verkettung -> Fix in der Single-Chain deckt beide
  Pfade ab.
- Bei jeder Exception faellt _export_with_filtergraph (Zeile 913-923) auf
  _export_optimized_concat zurueck (B-603-Sicherheitsnetz) -> daher "still 0 Frames ->
  Hard-Cut".

### Datenfluss (Beweis app94_segs.json, Gruppe 1 = Segmente 12-23)
crossfade-Muster [0,0,0,0,1,1,1,0,0,0,0,0]. Erzeugte Kette (real reproduziert):
[v0][v1]concat[xf0]; [xf0][v2]concat[xf1]; [xf1][v3]concat[xf2];
[xf2][v4]xfade=...offset=15.9056[xf3]; [xf3][v5]xfade..[xf4]; [xf4][v6]xfade..[xf5];
[xf5][v7]concat[xf6]; ... [xf9][v11]concat[xf10].

## Root cause (ffmpeg-belegt, real reproduziert)

Echter ffmpeg-8.1.1-Lauf mit den 12 realen Clips der Gruppe 1 liefert:
  [Parsed_xfade_51] First input link main timebase (1/1000000) do not match the
                    corresponding second input link xfade timebase (1/30)
  [Parsed_xfade_51] Failed to configure output pad on Parsed_xfade_51
  [out#0/mp4] Nothing was written into output file ... frame=0 ... Conversion failed!

Mechanismus (belegt):
- Der fps-Filter an jedem Segment (fps={fps}, Zeile 1008) setzt die Stream-Timebase
  auf 1/fps (hier 1/30).
- Der concat-Filter normalisiert seinen Output auf AV_TIME_BASE = 1/1000000
  (Mikrosekunden) - libavfilter-Standard fuer concat.
- xfade verlangt, dass BEIDE Input-Links dieselbe Timebase haben. In der gemischten
  Kette kommt der erste xfade-Input aus einem concat-Knoten (tb 1/1000000), der zweite
  direkt aus einem [vi]-fps-Filter (tb 1/30) -> Timebase-Konflikt -> xfade verweigert die
  Konfiguration -> 0 Frames.

Kein PTS-/Offset-/Framerate-/SAR-Problem: Offsets (15.9/19.06/22.72) sind korrekt, alle
Streams sind bereits auf gleiche Aufloesung/SAR/fps standardisiert. Es ist ausschliesslich
das Timebase-Label zwischen concat- und fps-Output.

Warum reine Ketten funktionieren:
- Reine xfade-Kette: kein concat-Knoten -> beide xfade-Inputs aus fps/xfade-Nodes,
  alle tb 1/fps -> Match.
- Reine cut-Kette: nur concat-Knoten, kein xfade -> concat akzeptiert beliebige tb und
  normalisiert selbst -> kein Match-Zwang.

B-707 ist keine B-687-Regression: bestaetigt - git show 8cb5786 (vor B-687) baut dieselbe
gemischte concat+xfade-Kette und failt identisch. B-687 hat die Timebase-Frage nie beruehrt.

## Variants

### Variant A - Timebase-Normalisierung an concat-Knoten (EMPFOHLEN)
An jeden concat-Knoten in _export_with_filtergraph ",settb=1/{fps}" anhaengen, damit der
concat-Output wieder auf die fps-Timebase (1/fps) der [vi]-Streams zurueckgesetzt wird ->
nachfolgender xfade sieht identische Timebase.
- Files: services/export_service.py - 2 Konstruktions-Sites: Zeile 1045 (erstes Paar
  concat), Zeile 1063-1065 (Loop-concat). Batched- und Single-Segment-Pfad automatisch abgedeckt.
- Neue/entfernte Deps: keine.
- Real bewiesen: Gruppe 1 rendert 43.500 s (Sigma(slot)=43.184 s, Rest = xfade-Tail/
  fps-Rundung), Offsets korrekt, >0 Frames.
- Effort: S
- Risk: P2 - reine-cut-Ketten bekommen settb an ihre concat-Knoten (Regressionstest noetig,
  aber semantisch neutral: reines concat->encode). Rand-Fall fraktionaler fps (z.B. 29.97)
  -> settb=1/29.97 traefe evtl. nicht exakt die reduzierte fps-Filter-tb; in der Praxis ist
  Export-fps ganzzahlig (Default 30.0, Preset 24/25/30/60) -> settb=1/30.0 parst und matcht
  (real bewiesen).
- Reversibel: leicht (2 String-Suffixe).
- B-687-Impact: null. xfade-Offset-Arithmetik, ext/eff_dur unveraendert; reine-xfade-Kette
  hat keine concat-Knoten -> nicht angefasst.

### Variant B - Homogene Sub-Chain-Split + concat-Demux
Jede Gruppe intern an cut/xfade-Grenzen in gleichartige Sub-Ketten (all-cut ODER all-xfade)
splitten, jede Sub-Kette als Zwischendatei rendern, dann per concat-Demuxer verketten.
- Files: services/export_service.py - groessere Umstrukturierung + neue Split-Logik.
- Effort: L
- Risk: P1 - B-687-Overlap-Arithmetik muss ueber Sub-Chain-Grenzen neu hergeleitet werden
  (acc/offset/ext springen an jeder Grenze); Temp-File- und Re-Encode-Explosion; langsamer.
- Reversibel: mittel.

### Variant C - Uniform AVTB auf allen Knoten
settb=AVTB an JEDEN [vi]-Segment-Filter UND jeden concat-Knoten -> alle Nodes teilen
1/1000000, xfade matcht immer, unabhaengig vom fps-Wert (robust gegen fraktionalen fps).
- Files: services/export_service.py - Segment-Filter (Zeile 1014) + alle concat-Sites.
- Real bewiesen: rendert ebenfalls korrekt (identische Dauer wie A).
- Effort: S-M
- Risk: P2 - beruehrt den funktionierenden Segment-Filter -> groessere Regressionsflaeche
  (reine-xfade-, reine-cut-, Single-Segment-Pfad alle betroffen). Dafuer fps-Wert-robust.
- Reversibel: leicht.

## Recommendation
Variant A. Kleinste Aenderungsflaeche, repariert den gemischten Fall exakt am Root-Cause
(concat->xfade-Timebase). Der haeufige, funktionierende reine-xfade-Pfad wird NICHT angefasst
(kein concat-Knoten). Real bewiesen: korrekte Dauer + Offsets + >0 Frames. B-687-Logik bleibt
bit-identisch. Variant C ist robuster gegen fraktionalen fps, kostet aber Regressionsflaeche
am Segment-Filter - nur noetig, falls je fraktionaler Export-fps eingefuehrt wird (aktuell
nicht der Fall). Variant B loest dasselbe mit deutlich mehr Komplexitaet, Temp-I/O und
B-687-Risiko - nicht gerechtfertigt.

Acceptance-Coverage Variant A:
- [x] Gemischte Gruppe rendert >0 Frames - real bewiesen (43.5 s).
- [x] Crossfades an richtigen Uebergaengen - Offsets 15.9/19.06/22.72 unveraendert korrekt.
- [x] ffprobe ~ Sigma(slot) - 43.5 s vs 43.184 s.
- [x] B-687-Overlap greift weiter - ext/eff_dur/offset-Code unberuehrt.
- [~] Reine cut-Gruppe - settb an concat neu; muss Regressionstest bestaetigen (P2).
- [x] Reine xfade-Gruppe - kein concat-Knoten -> unberuehrt.
- [~] Batched + 94 Segmente - muss echter ffmpeg-Lauf bestaetigen (verify).

## Cross-team impact
- Video/Export: einzige betroffene Ebene; Filtergraph-Konstruktion.
- ML/GPU: keine. Encoder/hwaccel/_video_encode_args() unberuehrt (h264_nvenc/libx264-Fallback
  bleibt). settb ist reine Timestamp-Metadaten-Operation, kein Decode/Encode.
- Pacing/Audio: keine. Beat-Anker (offset==start[i]) unveraendert; Audio-Mux/LUFS unberuehrt.

## Open questions for user
- Ist Export-fps garantiert immer ganzzahlig? (Default 30.0; falls je 29.97/fraktional geplant,
  dann Variant C statt A.) - sonst keine offenen Fragen; Root-Cause + Fix sind real bewiesen.
