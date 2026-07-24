# Implementation plan: b687-crossfade-av-sync (B-687 Defekt 1)

Gewaehlte Variante: A - Export-seitige Overlap-Extension (Tail aus Restmaterial).
Scope strikt: NUR services/export_service.py::_export_with_filtergraph
(Single-Chain-Zweig). Concat/Cut-Pfad und pacing_service UNBERUEHRT.

## Pre-checks
- [ ] Worktree PB_studio_Rebuild_sandbox_b687-crossfade-av-sync existiert, Branch
      sandbox/b687-crossfade-av-sync, sauber (git status --short --branch).
- [ ] Baseline erfassen: aktuellen Crossfade-Export mit Test-Material rendern und
      ffprobe-Dauern (Video vs Audio) nach _sandbox_meta/baseline/ schreiben,
      um den Drift VOR dem Fix zu belegen.
- [ ] conda-env pb-studio aktiv (Python 3.10, torch 1.12.1+cu113), ffmpeg/ffprobe
      auf PATH (FFMPEG-Konstante in export_service.py).

## Steps

1. **services/export_service.py::_export_with_filtergraph** (Block :956-:1016)
   - WAS: Vor dem Bau der xfade-Kette eine effektive Segment-Dauer eff_dur[]
     berechnen, die den Overlap-Tail einrechnet, und den ffmpeg-Input-`-t` (:939)
     sowie seg_durations (:969) auf eff_dur umstellen. xfade_dur zusaetzlich auf
     den real vorhandenen Tail (ext) clampen.
   - WARUM: Composite = Sigma(slot+ext) - Sigma xfade = Sigma slot = Audiodauer;
     offset landet auf der Beat-Grenze; kein Freeze/Over-Read.
   - Code-Skizze (<=15 Zeilen, konzeptionell):
       n = len(video_segments)
       ext = [0.0] * n
       for i in range(n - 1):
           xf_next = min(video_segments[i+1].get("crossfade", 0.0) or 0.0, 2.0)
           base = video_segments[i].get("source_duration",
                                        video_segments[i]["end"] - video_segments[i]["start"])
           clip_dur = video_segments[i].get("duration")
           ss = video_segments[i].get("source_start", 0.0)
           avail = (clip_dur - (ss + base)) if clip_dur else xf_next
           ext[i] = max(0.0, min(xf_next, avail))
       eff_dur = [
           (video_segments[i].get("source_duration",
             video_segments[i]["end"] - video_segments[i]["start"]) + ext[i])
           for i in range(n)
       ]
     - Input-Args (:934-:939): -t = eff_dur[i] statt source_duration.
     - seg_durations (:969-:972) = eff_dur.
     - xfade_dur-Clamp (:988 und :1003): zusaetzlich `, ext[i-1]` in das min() (der
       Tail des OUTGOING Segments begrenzt den Crossfade), also
       xfade_dur = min(crossfade, 2.0, seg_durations[i], accumulated, ext[i-1]).
       Faellt ext[i-1] unter eine Mindest-Schwelle (< 0.1 s), harter Schnitt
       (concat-Zweig, wie schon vorhanden) statt Mikro-Crossfade.
   - Test: tests/test_services/test_b687_d1_av_length.py::
       test_composite_equals_sum_of_slots  (siehe Test-Plan Unit 1)

2. **services/export_service.py::_export_with_filtergraph** - Backward-Compat Guard
   - WAS: eff_dur/ext-Logik defensiv gegen fehlendes "duration"-Feld (Test-Helper
     ohne clip.duration) machen: fehlt "duration", avail = xf_next (Material als
     vorhanden annehmen). KEINE Exception.
   - WARUM: Robustheit; verhindert Regress in Tests/Aufrufern ohne clip.duration.
   - Test: abgedeckt durch Unit 2/3.

3. **KEINE Aenderung** an _export_optimized_concat, _export_with_filtergraph_batched
   (delegiert bereits an Single-Chain -> erbt Fix), _prepare_audio_entry_for_timeline,
   pacing_service.py, export/_common.py.
   - Begruendung: AK3/AK6 + HARTREGEL "nur explizit angewiesene Aenderungen".

4. **tests/test_services/test_b687_xfade_offset_clamp.py** - anpassen
   - WAS: _seg-Helper um "duration" ergaenzen; Erwartungswerte fuer Offsets/Durs an
     die neue Beat-Anker-Semantik anpassen (offset_i ~ start[i]).
   - WARUM: Test kodiert die alte D2-Offset-Semantik; nach Beat-Anker-Umstellung
     sonst falsch-rot. D2-SCHUTZ-Assertion (kein Kollaps auf 0.1-Floor, xfade nie >
     Segment) MUSS erhalten bleiben.
   - HINWEIS: Test-Aenderung vorab dem User bestaetigen lassen (OF2).

## Test-Plan

### Unit (schnell, ohne echtes ffmpeg - _run_ffmpeg gemockt wie bestehender D2-Test)
- Unit 1 (neu, test_b687_d1_av_length.py):
  Segmente back-to-back mit "duration" gross genug; parse -filter_complex + -t-Args
  aus dem cmd. Assertions:
  * Sigma(-t) - Sigma(xfade_dur) == Sigma slot (+-1e-6)  -> Laenge korrekt.
  * jeder offset_i == start[i] (+-1e-3)                  -> Beat-Anker (AK2).
- Unit 2 (neu): Clip-Ende ohne Tail (source_start+source_duration == duration):
  ext == 0 -> Crossfade an diesem Uebergang == 0 (harter Schnitt), kein Over-Read
  (-t <= duration - source_start), keine Exception.
- Unit 3 (angepasst, s. Step 4): D2-Kollaps-Schutz bleibt gruen.
- Regression: test_a1_crossfades_and_transition_settings.py,
  test_cycle6_export_batch.py, test_b397_export_timeline_gap_validation.py,
  test_optb_default_hard_cuts.py laufen unveraendert gruen (AK3).

Batch-Kommando (ein Lauf, Regel "Tests buendeln"):
  pytest tests/test_services/test_b687_xfade_offset_clamp.py \
         tests/test_services/test_b687_d1_av_length.py \
         tests/test_services/test_a1_crossfades_and_transition_settings.py \
         tests/test_services/test_cycle6_export_batch.py \
         tests/test_services/test_b397_export_timeline_gap_validation.py \
         tests/test_services/test_optb_default_hard_cuts.py -q

### Integration / Live-Verify (echtes ffmpeg, Pflicht vor "verified")
Test-Material (aus Memory reference_test_dataset):
  - Video-Ordner: Solo_Natur (103 Dateien)
  - Audio: "Crusty Progressive Psy Set2.mp3" (149 MB DJ-Mix)
Ablauf:
  1. Projekt mit diesem Material, transition_type != "cut" (Crossfade-Modus),
     langer Auto-Edit (>50 Segmente -> triggert AUCH batched-Pfad, AK5).
  2. export_timeline -> out.mp4.
  3. ffprobe-Metriken erfassen und vergleichen:
     - Video-Dauer: ffprobe -v error -select_streams v:0 -show_entries
       format=duration / stream=duration,nb_frames -of default=nw=1 out.mp4
     - Audio-Dauer: gleiches fuer a:0.
     - AK1: |video_dur - audio_dur| <= 1/fps (~33 ms @30fps).
  4. Sicht-Check: Beat-Cut am Track-ENDE liegt noch auf dem Beat (kein Vorlauf).
  5. Freeze-Check: kein eingefrorenes Bild an Uebergaengen (AK4) - visuell +
     optional Frame-Diff-Stichprobe an 3 Uebergaengen.
  6. Batched-Grenzen: Uebergaenge an Batch-Grenzen (alle 12 Segmente) sind harte
     Cuts (erwartet, B-603), KEIN Drift.
Ergebnisse nach _sandbox_meta/results/verify_log.md (Video-/Audio-Dauern, Delta,
Sicht-Check-Notizen, ffprobe-Rohausgabe).

### Baseline-Gegenprobe
Gleicher Export VOR dem Fix (git stash / Baseline-Branch) -> Drift dokumentieren
(erwartet: video_dur < audio_dur um ~Sigma xfade). Beleg, dass der Fix wirkt.

## Rollback
- Worktree-Branch verwerfen (git worktree remove / branch delete) - kein main-Impact.
- Keine DB-Migration, keine persistente Aenderung -> Rollback = reines Zuruecknehmen
  der export_service.py-Diff. Bestehende Timelines bleiben unveraendert nutzbar.

## Done-Definition
- Alle Akzeptanzkriterien AK1-AK6 gruen und in verify_log.md belegt (echtes ffmpeg,
  nicht nur Unit-Mock).
- Skeptiker-Risiken <= P2 (P0/P1 aus Varianten B/C/D bewusst nicht gewaehlt).
- Concat/Cut-Regressionstests gruen (AK3).
- status: fixed setzt NUR der User (HARTREGEL).
