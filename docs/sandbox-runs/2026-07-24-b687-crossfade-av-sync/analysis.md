# Analysis: b687-crossfade-av-sync (B-687 Defekt 1)

## Ziel
A/V-Sync im Crossfade-Export korrigieren. Aktuell schrumpft die Video-Gesamtdauer
um die Summe aller Crossfade-Dauern (Composite = Sigma slot - Sigma xfade), waehrend
das Audio in voller Laenge gemuxt wird (-shortest). Ergebnis: Bild laeuft dem Ton
progressiv voraus, Beat-Cuts driften vom Beat weg. Video- und Audio-Gesamtdauer
muessen wieder uebereinstimmen, ohne die Beat-Verankerung der Cuts zu zerstoeren
und ohne den Concat/Cut-Pfad zu beruehren.

## Akzeptanzkriterien
- [ ] AK1: ffprobe-Videodauer ~ ffprobe-Audiodauer (Delta <= 1 Frame ~ 33 ms @30fps)
      bei langem Crossfade-Export (viele aktive Crossfades).
- [ ] AK2: Beat-Cuts bleiben beat-verankert (nicht-driftend); Crossfade beginnt an
      der Beat-Grenze (Slot-Uebergang), nicht davor.
- [ ] AK3: Concat/Cut-Pfad (transition_type="cut", _export_optimized_concat) bleibt
      unveraendert.
- [ ] AK4: Kein Freeze-/Doppel-Frame, keine gestapelten Segmente (D2-Schutz bleibt).
- [ ] AK5: Batched-Pfad (_export_with_filtergraph_batched, >12 Segmente) erbt den Fix.
- [ ] AK6: Bestehende Timelines in der DB profitieren OHNE Neu-Pacing.

## Aktueller Zustand

### Datenfluss
export_timeline / export_preview (export_service.py) laden TimelineEntry
(Skalar-Spalten) -> bauen video_segments-Dicts (:343, :1480) mit Feldern:
path, start, end (Timeline-Slot), duration (= clip.duration), source_start,
source_duration, crossfade, brightness, contrast. source_duration kommt aus
_source_duration_from_entry (export/_common.py:83) = source_end - source_start,
Fallback Timeline-Dauer.

Beide Einstiege routen nach has_effects:
- Effekte (Crossfade/Brightness/Contrast) -> _export_with_filtergraph (:873)
- sonst -> _export_optimized_concat (:418, KEIN Drift, unberuehrt lassen).

_export_with_filtergraph:
- len > XFADE_BATCH_SIZE(12) -> _export_with_filtergraph_batched (:706), das pro
  Batch (<=12) rekursiv _export_with_filtergraph (Single-Chain) aufruft und die
  Batch-Zwischendateien per concat -c:v copy verkettet (Batch-Grenzen = harter
  Schnitt, bewusst, B-603).
- Single-Chain (:926+): pro Segment -ss source_start -t source_duration -i path,
  Filtergraph baut xfade-Kette (:980-:1016).

### xfade-Arithmetik (verifiziert)
- xfade-Output-Laenge = offset + Laenge(2. Input).
- accumulated_duration startet = seg_durations[0].
- Pro Uebergang: offset = max(0.1, accumulated - xfade_dur), danach
  accumulated = accumulated + seg_durations[i] - xfade_dur.
- Daraus folgt Composite = Sigma seg_durations - Sigma xfade_dur.
- xfade_dur = min(crossfade, 2.0, seg_durations[i], accumulated) (D2-Clamp, bereits
  gefixt, verhindert negativen Akkumulator).

### Warum der Drift entsteht
Segment i liefert nur slot_i Material (source_duration ~ end-start, weil
_validate_video_timeline_gaps back-to-back erzwingt, Luecken <= 0.05 s). Der
Crossfade frisst sich in slot_i HINEIN (offset = accumulated - xfade), statt NACH
slot_i zu passieren. Es fehlt xfade Sekunden Tail-Material pro Uebergang. Audio wird
voll gemuxt (-map 1:a:0 ... -shortest, :1042-1043, :655, :830) -> -shortest kappt das
Audio-Ende, Bild eilt vor.

### Material-Verfuegbarkeit (Pacing, verifiziert)
pacing_service.py:1624: source_end = min(source_start + seg_duration, vid_duration)
und clip_offsets[vid] = source_end (:1685) -> Clips werden sequenziell verbraucht.
Tail-Material (clip.duration - source_end) ist bei natuerlichen Clips (Solo_Natur)
meist vorhanden, aber am Clip-Ende exakt 0. Der Fix muss ehrlich clampen (kein
Over-Read ueber clip.duration).

### Betroffene Tests
- tests/test_services/test_b687_xfade_offset_clamp.py - kodiert die ALTE
  Offset/Clamp-Semantik (D2). Beat-Anker-Umstellung aendert Offsets/Durs -> MUSS
  mit-angepasst werden (ehrlich flaggen, nicht heimlich brechen).
- tests/test_services/test_a1_crossfades_and_transition_settings.py
- tests/test_services/test_cycle6_export_batch.py
- tests/test_services/test_b397_export_timeline_gap_validation.py

### Luecken / Unbekannte
- Kein bestehender Test prueft Video-vs-Audio-GESAMTDAUER nach echtem ffmpeg-Run.
- _export_with_filtergraph_batched ist laut B-603-Kommentar noch UNVERIFIZIERT mit
  echtem ffmpeg -> Live-Verify noetig.

## Varianten

### Variant A - Export-seitige Overlap-Extension (Tail aus Restmaterial) [EMPFOHLEN]
Ansatz. Rein in _export_with_filtergraph: jedes Segment i (ausser dem letzten in der
Kette) bekommt fuer den -t/seg_durations-Wert einen Tail von
ext_i = min(crossfade_{i+1}, 2.0, verfuegbares Restmaterial), wobei
verfuegbar = clip.duration - (source_start + source_duration). Der xfade verbraucht
genau diesen Tail. Composite = Sigma(slot_i + ext_i) - Sigma xfade = Sigma slot =
Audiodauer, und offset landet exakt auf start[i+1] (Beat-Grenze). Reicht das Material
an einer Clip-Grenze nicht (ext < crossfade), wird der Crossfade an GENAU diesem
Uebergang auf ext reduziert (ehrliche Degradation, im Extremfall harter Schnitt) -
nie ein Freeze.
- Files: services/export_service.py (_export_with_filtergraph, :926-:1048).
- Neue Deps: keine.
- Effort: S-M.
- Risk: P1 (Filtergraph-Math, testbar) / P2 (Material-Clamp).
- Reversibel: leicht (eine Funktion, kein DB-/Schema-Eingriff, kein Re-Pacing).

Warum korrekt (Arithmetik). L_i = slot_i + ext_i, ext_last = 0, xfade_dur_i =
ext_{i-1}. Dann offset_1 = L_0 - xfade = slot_0 = start[1], induktiv
offset_i = Sigma_{j<i} slot_j = start[i]; Final accumulated = Sigma slot.
-> Laenge stimmt UND jeder Crossfade startet auf dem Beat (gleicher Anker wie der
harte Cut im Concat-Pfad).

### Variant B - Audio auf Video-Laenge kuerzen
Ansatz. Audio auf Sigma slot - Sigma xfade trimmen, sodass beide gleich lang sind.
- Files: export_service.py (Audio-Prep + alle 3 -shortest-Muxes).
- Effort: S.
- Risk: P0 fachlich - kuerzt/staucht die Musik gegen ihre eigenen Beats. Cuts wurden
  auf das ORIGINAL-Audio-Grid gepacet; getrimmtes Audio verschiebt die Beats gegen
  die Cuts -> desynct GENAU das, was der Fix retten soll. Nur "gleich lang", nicht
  "synchron".
- Reversibel: leicht, aber inhaltlich falsch.
- VERWORFEN (loest AK2 nicht, verletzt Musik-Integritaet).

### Variant C - Timeline-Anker-Offsets (offset = start[i]) ohne Extra-Material
Ansatz. offset aus seg["start"] statt kumulativem Akkumulator. Drift nicht-kumulativ.
- Files: export_service.py (_export_with_filtergraph Offset-Berechnung).
- Effort: S.
- Risk: P1-P0 - OHNE Tail-Material ist start[i+1] > accumulated (um bisheriges
  Sigma xfade). xfade mit offset > Laenge(1. Input) HAELT den letzten Frame des 1.
  Inputs (Freeze), bis der Offset erreicht ist -> pro Uebergang ein Freeze von
  ~xfade, kumuliert genau die vorher verlorene Zeit. Beats bleiben verankert, aber
  sichtbare eingefrorene Frames statt Bewegung. Video-Gesamtdauer stimmt dann zwar
  (Freeze fuellt auf), aber Bildqualitaet degradiert sichtbar.
- Reversibel: leicht.
- Bewertung: ehrliche Teilloesung (kein Drift, Beats verankert) ABER Freeze-Frames
  sind ein NEUER sichtbarer Defekt. Nur akzeptabel wo Material fehlt - genau das ist
  der Fallback INNERHALB von Variant A.

### Variant D - Overlap im Pacing-Builder persistieren
Ansatz. pacing_service.py setzt source_end = source_start + slot + crossfade
(Timeline-start/end bleiben back-to-back), Overlap-Tail schon in der DB.
- Files: pacing_service.py (:1624, :1658), evtl. export/_common.py (Validierung),
  Preview/UI-Konsumenten.
- Effort: L.
- Risk: P1 breit - (a) source_end kann vid_duration ueberschreiten ->
  _source_duration_from_entry wirft (0.05 s Toleranz), Clamp noetig; (b) clip_offsets
  verschiebt sich -> aendert Segment-AUSWAHL nachfolgender Segmente (visuelle
  Regression); (c) bestehende Timelines profitieren NICHT ohne Neu-Pacing (verletzt
  AK6); (d) jeder Konsument der Felder (Thumbnails, Timeline-Breite, Preview) sieht
  laengere Source-Ranges.
- Reversibel: schwer (DB-Werte, Auswahl-Aenderung).
- Bewertung: konzeptionell "an der Quelle korrekt", aber grosse Blast-Radius und
  bricht AK6. Overlap gehoert an die Render-Grenze, nicht in die persistierte
  Timeline.

## Empfehlung
Variant A. Einzige Variante, die ALLE Akzeptanzkriterien erfuellt:
- AK1 (Laenge): Composite = Sigma slot = Audio (arithmetisch bewiesen).
- AK2 (Beat-Anker): Crossfade startet exakt auf start[i+1] - gleicher Anker wie der
  harte Cut im Concat-Pfad.
- AK3 (Concat unberuehrt): Aenderung nur in _export_with_filtergraph.
- AK4 (kein Freeze/Stapel): D2-Clamp bleibt, zusaetzlich xfade <= ext -> Tail immer
  real vorhanden.
- AK5 (batched): Batched delegiert pro Batch an Single-Chain -> erbt den Fix
  automatisch (jede Batch-Zwischendatei = Sigma slot_batch; Batch-Grenzen bleiben
  harte Cuts ohne Drift).
- AK6 (Bestandsdaten): keine DB-Aenderung, kein Re-Pacing.
Reversibel, klein, testbar. Variant C ist der eingebaute Notnagel (Freeze) NUR dort
wo Material fehlt; Variant B verworfen; Variant D zu breit und AK6-brechend.

Was die anderen verlieren: B opfert Musik-Sync (Kern-Ziel). C erzeugt sichtbare
Freeze-Frames. D braucht Re-Pacing und aendert die Bildauswahl bestehender Projekte.

## Cross-Team-Impact
- Video: Crossfade-Uebergaenge zeigen jetzt echtes Fortsetzungs-Material im Tail
  (statt frueh abzublenden). Bei aufeinanderfolgenden Segmenten desselben Clips
  blendet der Clip mit einem minimal spaeteren Teil seiner selbst - unauffaellig.
- Audio: Keine Aenderung an der Audiospur (bleibt voll). -shortest kappt nichts mehr,
  weil Video jetzt gleich lang ist.
- Pacing: unberuehrt (bewusst - Fix an der Render-Grenze, nicht an der Quelle).
- Platform/GPU: irrelevant; keine Encoder-/hwaccel-Aenderung (NVENC via
  _video_encode_args() bleibt).

## Offene Fragen / Risiken
- OF1: Bei fehlendem Tail-Material Crossfade auf ext reduzieren (empfohlen) ODER auf
  harten Schnitt (0)? Empfehlung: auf ext reduzieren, unter Mindest-Schwelle (< 0.1 s)
  auf harten Cut.
- OF2: Bestehender D2-Test kodiert alte Semantik und MUSS angepasst werden. OK?
- R1: _export_with_filtergraph_batched laut B-603-Kommentar noch nicht mit echtem
  ffmpeg verifiziert -> Live-Verify im Batched-Pfad zwingend.
- R2: seg["duration"](= clip.duration) muss im Seg-Dict vorhanden sein; ist es in
  Prod (:347, :1484), aber nicht im Test-Helper -> Test-Helper ergaenzen.
