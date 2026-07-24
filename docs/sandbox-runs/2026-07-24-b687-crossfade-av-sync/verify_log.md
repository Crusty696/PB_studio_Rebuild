# Verify-Log — B-687 Defekt 1 / Variant A

Durchgefuehrt vom Haupt-Agent (der sandbox-verifier-Subagent starb an einem
API-Fehler; Verifikation daher direkt ausgefuehrt). Stand: 2026-07-24.

## AK1 — Video-Gesamtdauer == Sigma(slot) == Audiodauer (echtes ffmpeg)

Setup (synthetisch, encoderunabhaengige Laengenmessung):
- 5 Testclips `testsrc=duration=6:size=320x240:rate=30` (clip.duration=6.0s).
- 5 Segmente, Slot je 2.0s, back-to-back (start 0/2/4/6/8), crossfade=1.0s,
  source_start=0, source_duration=2.0, duration=6.0.
- Sigma(slot) = 10.0s (== erwartete Audiodauer). 4 Crossfades a 1.0s.
- Aufruf: `_export_with_filtergraph(segs, None, out, 320,240,30, None, 5)` (audio_path=None -> -an).
- Messung: `ffprobe -v error -select_streams v:0 -show_entries format=duration` + `-count_frames nb_read_frames`.

Ergebnis:

| Variante | ffprobe duration | nb_read_frames | Delta zu 10.0s |
|----------|------------------|----------------|----------------|
| Baseline (main, 0140bf7) | 6.000000 s | 180 | -4.000 s (= Sigma xfade) |
| Worktree (Variant A)     | 10.000000 s | 300 | 0.000 s |

Interpretation: Baseline verkuerzt das Video um die volle Crossfade-Summe (4x1.0s)
-> genau der A/V-Drift von B-687 D1. Variant A liefert exakt Sigma(slot)=10.000s
(300 Frames @ 30fps) -> Video- und Audiodauer stimmen ueberein, Delta 0 < 1 Frame.
**AK1 erfuellt.**

## AK3 — Regression Export-Pfade gruen (Unit)

`pytest tests/test_services/{test_b687_d1_av_length, test_b687_xfade_offset_clamp,
test_a1_crossfades_and_transition_settings, test_cycle6_export_batch,
test_b397_export_timeline_gap_validation, test_optb_default_hard_cuts}.py`
-> **13 passed** (36.31s). Concat/cut-Pfad + Crossfade-Settings + Gap-Validator +
Hard-Cut-Default unveraendert. Committer D2-Test unveraendert gruen (OF2 entfaellt).

## Offen (User-Live-Verify, nicht automatisierbar hier)
- Voller App-Export mit Echt-Material (Solo_Natur + "Crusty Progressive Psy Set2.mp3"),
  Crossfade-Modus, langer Auto-Edit >50 Segmente (triggert auch batched-Pfad):
  ffprobe Video- vs. Audiodauer, Beat-Cut am Track-Ende auf dem Beat, Freeze-Check an
  Uebergaengen, NVENC-Encode real. Das ist der finale Live-Verify-Schritt des Users.

## Verdikt
AK1 (Laenge/Sync) mit echtem ffmpeg belegt, AK3 (Regression) gruen. Apply-ready
vorbehaltlich Skeptiker-Urteil (risks.md) und User-Live-Verify.
