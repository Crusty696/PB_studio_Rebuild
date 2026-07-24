# Risks: b687-crossfade-av-sync (B-687 Defekt 1, Variant A)

## Verdict
proceed-with-conditions — kein P0, kein P1. Arithmetik verifiziert, alle
Unit-/Regressions-Tests gruen. Offen bleibt der PFLICHT-Live-Verify mit echtem
ffmpeg (AK1/AK4/AK5), den kein Mock-Test ersetzt. Restrisiken sind P2/P3.

## P0 — blockers
- keine. (Ueber-Read, Over-Length am Hard-Cut, Batched-Drift, Randfaelle alle
  einzeln geprueft und widerlegt — siehe unten.)

## P1 — silent regressions
- keine belegbar. Der plausibelste P1-Kandidat (Over-Length/Drift am
  Hard-Cut-Rueckfall, Skeptiker-Punkt 3) ist arithmetisch AUSGESCHLOSSEN:
  `ext[i-1]` ist immer der bindende Term im `min()` fuer `xfade_dur`.
  Beweis: `ext[i-1] = min(crossfade_i, avail, base_{i-1}, slot_i)` und
  `xfade_dur = min(crossfade_i, seg_durations[i]=slot_i+ext[i], accumulated, ext[i-1])`.
  Es gilt `ext[i-1] <= crossfade_i`, `ext[i-1] <= slot_i <= seg_durations[i]`,
  `ext[i-1] <= slot_{i-1} <= accumulated`. Also `xfade_dur == ext[i-1]` exakt.
  `ext` ist per Konstruktion 0 ODER >= 0.1 -> nie im Bereich (0,0.1). Damit kann
  der Fall "eff_dur[i-1] verlaengert, aber xfade < 0.1 -> Over-Length" nicht
  auftreten. Empirisch bestaetigt (`export_service.py:951-1042`, Sim n2/notail).

## P2 — quality / latente Risiken
- **P2-1 Rest-Drift bei erlaubten Mini-Luecken (Skeptiker-Punkt 6).**
  `export_service.py:1027,1044` — `offset_i == Sigma(source_duration_{j<i})`,
  NICHT `== seg["start"][i]`. Die Gleichheit `offset == start` gilt nur bei
  luekenlosen Slots. `_validate_video_timeline_gaps` erlaubt <=0.05 s Luecke pro
  Uebergang; diese akkumulieren.
  Beleg (Sim, 5 Segmente je 0.05 s Luecke):
  offsets `[2.0,4.0,6.0,8.0]` vs. echte starts `[2.05,4.1,6.15,8.2]`
  -> 0.2 s kumulierter Versatz Video-Cut gegen Audio-Beat am 5. Segment.
  Bei 100 Segmenten theoretisch bis ~5 s. ABER: (a) Pacing erzwingt normalerweise
  back-to-back (Luecke ~0), 0.05 ist Float-Toleranz; (b) der Versatz ist
  PRE-EXISTING (vor dem Fix war Composite = Sigma src - Sigma xfade, gleiche
  Gap-Akkumulation), also KEINE neue Regression. AK2 "beat-verankert" gilt streng
  nur gapless. Empfehlung: im Live-Verify die kumulierte Luecke des echten
  Test-Materials messen (`Sigma(source_duration)` vs. Track-Laenge); wenn > 1
  Frame, ist AK1 nicht durch diesen Fix allein erreichbar.

- **P2-2 Over-Read wenn `"duration"` fehlt/falsy (Skeptiker-Punkt 1).**
  `export_service.py:956` — `_avail = (clip_dur - (ss+base)) if _clip_dur else _xf_next`.
  Fehlt "duration" oder ist es 0/None, wird Material als vorhanden ANGENOMMEN
  (`avail = xf_next`) -> `-t = source_duration + ext` kann die echte Datei
  ueberlesen (schwarze/eingefrorene Frames am Clip-Ende). Beleg (Sim
  "no-duration"): `-t[0] = 3.0` bei source_duration 2.0.
  ENTSCHAERFT in Prod: beide Seg-Dict-Builder setzen `"duration": clip.duration
  or 10.0` (`:347`, `:1523`) -> immer truthy, nie 0/None. Kein Prod-Pfad triggert
  den Fallback. Latent fuer kuenftige Aufrufer ohne "duration". Zusatzrisiko: ist
  `clip.duration` in der DB GROESSER als die echte Datei (stale Probe), ist avail
  zu gross -> ebenfalls Over-Read. Empfehlung: Fallback konservativ auf `avail=0`
  (statt xf_next) setzen, ODER Kommentar/Assert, dass "duration" Pflicht ist.

- **P2-3 Verhaltensdrift `> 0` -> `>= 0.1` bei kleinen Crossfades
  (Skeptiker-Punkt 3, Nebenbefund).** `:1026,1043` — Schwelle von `xfade_dur > 0`
  auf `>= 0.1` angehoben. Ein bewusst gesetzter Mini-Crossfade (z.B. 0.08 s) mit
  vorhandenem Material wird jetzt zum harten Schnitt statt Mikro-Crossfade. Durch
  OF1 gedeckt und praktisch unsichtbar, aber es ist eine Semantik-Aenderung ueber
  den reinen Drift-Fix hinaus. Nur Doku-relevant.

- **P2-4 Preview-Fenster-Trim erweitert Tail ueber window_end (Skeptiker-Punkt
  5).** `:1516` kuerzt `source_duration` am Fensterende (nicht `duration`) ->
  `avail` steigt -> ein NICHT-letztes getrimmtes Segment koennte ext > erwartet
  bekommen und Clip-Material knapp hinter window_end zeigen. Kosmetisch (Preview),
  kein Over-Read der Datei, letztes Segment hat ext=0. P3-nahe.

## P3 — notes
- `source_start` None-Guard inkonsistent: ext-Berechnung (`:954`) faengt None mit
  `or 0.0`, der `-ss`/`-t`-Pfad (`:972-973`) NICHT (`None > 0.01` -> TypeError).
  PRE-EXISTING (Zeile unveraendert), Prod setzt `ve.source_start or 0.0` -> nie
  None. Kein neuer Defekt.
- `test_b687_xfade_offset_clamp.py` (D2) wurde entgegen Plan-Step 4 NICHT
  geaendert und ist trotzdem gruen (13/13). Der D2-Test hat keinen "duration"-Key
  -> laeuft durch den `avail=xf_next`-Fallback, ext dennoch durch slot_next
  geklammert. Plan-Aussage "D2-Test MUSS angepasst werden" war zu pessimistisch;
  kein Handlungsbedarf. Ehrlich: gut, dass nicht heimlich gebrochen.

## Batched-Pfad (Skeptiker-Punkt 2) — checked, none
`_export_with_filtergraph_batched` (:706) splittet in Gruppen <=12 und ruft
`_export_with_filtergraph` je Gruppe mit den GLEICHEN Seg-Dicts (Slices) ->
"duration"/source_* bleiben erhalten, Fix wird vollstaendig geerbt. Das
Gruppen-LETZTE Segment wird von `for _i in range(_n_seg-1)` NICHT iteriert ->
`ext=0` -> keine Verlaengerung, harter Schnitt an der Gruppengrenze (B-603
gewollt). Gruppen-Composite = Sigma(slot_gruppe) exakt (jeder ext von einem
xfade konsumiert); Concat aller Gruppen = Sigma(slot) = Audio. KEIN Over-Length
und KEINE Zusatz-Drift an Batch-Grenzen. Der am Boundary "verlorene" Crossfade
(seg[12].crossfade) war schon vor dem Fix ein harter Schnitt.

## Concat-Akkumulator (Skeptiker-Punkt 4) — checked, none
Gemischte crossfade/hard-cut-Uebergaenge: crossfade-Zweig
`accumulated += seg_durations[i] - xfade_dur`, concat-Zweig
`accumulated += seg_durations[i]`. Da im concat-Zweig `ext[i-1]==0` (sonst waere
xfade_dur=ext[i-1]>=0.1 -> crossfade-Zweig), gilt `seg_durations[i-1]=slot_{i-1}`
(keine ungenutzte Verlaengerung). Laengenbilanz bleibt Sigma(slot). Verifiziert
(Sim "n2 notail": ts=[0.3,2.0], concat=1, Composite=2.3-0=2.3=Sigma slot).

## Randfaelle (Skeptiker-Punkt 5) — checked, none
- n==1: `range(0)` leer -> ext=[0], eff_dur[0]=source_duration -> identisch zu
  vor dem Fix. Unveraendert.
- n==2 mit Material: Composite 3+2-1=4=Sigma slot, offset=2=start[1]. ok.
- alle crossfade==0 (effekt-only im Filtergraph): xf_next=0 -> ext alle 0 ->
  eff_dur=source_duration, alle Uebergaenge concat -> BIT-identisch zu vor dem
  Fix. Reiner Concat/Cut-Pfad (`_export_optimized_concat`) NICHT beruehrt (AK3).
- erstes/letztes Segment: ext[last]=0 immer; erstes Segment ext[0] nur wenn
  Material -> ok.

## Aufrufer/Tests (Skeptiker-Punkt 7) — checked, none
Aufrufer von `_export_with_filtergraph`: `:403` (export_timeline, has_effects),
`:1572` (export_preview), `:770` (batched-Rekursion). Alle liefern Seg-Dicts mit
"duration". Test-Aufrufer mocken `_run_ffmpeg`/`_prepare_normalized_audio`.
`test_cycle6_export_batch.py` prueft nur `inspect.getsource` (filter_complex_
script) -> von der -t/Filter-Aenderung unberuehrt. Gruen:
- test_b687_xfade_offset_clamp.py, test_b687_d1_av_length.py,
  test_b332_export_preview_first_video_offset.py,
  test_b580_export_warns_on_missing_clip.py, test_cycle6_export_batch.py (13/13)
- test_a1_crossfades_and_transition_settings.py,
  test_b397_export_timeline_gap_validation.py,
  test_optb_default_hard_cuts.py (5/5)

## Checked categories
- [x] Callsite coverage — 3 Prod-Callsites + 1 Rekursion + 5 Test-Callsites gescannt, 0 gebrochen
- [x] Side effects — kein GPU/DB/Thread-Impact; NVENC/hwaccel unveraendert; keine Schema-Aenderung
- [x] Behavioral drift — Randfaelle n1/n2/all-cut identisch; kleine-crossfade Schwelle (P2-3)
- [x] Migration/compat — keine DB-Aenderung, Bestandstimelines profitieren ohne Re-Pacing (AK6)
- [x] Test gaps — Unit deckt Laenge/Beat-Anker/Hard-Cut ab; LIVE-ffmpeg-Verify fehlt noch (Pflicht)
- [x] Plan logical gaps — Beat-Anker-Beweis gilt nur gapless (P2-1); Plan-Step4 unnoetig (P3)
- [x] PB Studio — Pacing/Brain V3/Schnitt unberuehrt; Scope strikt auf 1 Funktion

## Recommendations
1. Live-Verify mit echtem ffmpeg ist NICHT optional: AK1 (Video~Audio-Dauer),
   AK4 (kein Freeze), AK5 (Batched >12 Segmente, B-603 unverifiziert) muessen mit
   Solo_Natur + DJ-Mix real gemessen werden. Mock-Tests belegen nur die
   cmd-Konstruktion, nicht das Renderergebnis.
2. Im Live-Verify die kumulierte Slot-Luecke des Test-Materials messen
   (`Sigma(source_duration)` vs. Track-Laenge). Ist sie > 1 Frame, deckt der Fix
   AK1 nicht allein ab (P2-1) — dann separat entscheiden, nicht heimlich als
   "fixed" markieren.
3. Optional haerten: `avail`-Fallback bei fehlendem "duration" auf 0 statt
   xf_next (P2-2) — verhindert latenten Over-Read fuer kuenftige Aufrufer.
4. P2-3 (>=0.1-Schwelle) im Bug-/Decision-File dokumentieren, damit die
   Mikro-Crossfade-Semantikaenderung nachvollziehbar ist.
5. `status: fixed` erst nach Live-Verify durch den User (HARTREGEL).
