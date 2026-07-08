# Abschluss-Synthese — Audit-Fixplan 2026-07-07 (Stand 2026-07-08)

- **Plan:** `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`
- **Status:** `code-complete-live-pending` — alle für dieses Release vorgesehenen
  Code-Tasks umgesetzt, getestet, teils live bewiesen. `fixed` setzt der User
  nach eigener Sichtung.
- **Branch:** `codex/OTK-021-source-consolidation-2026-06-22`, gepusht bis
  `4422afa`.
- **Decision:** `wiki/decisions/D-064-audit-fixplan-und-vollintegration.md`.

## Ergebnis pro Task

| Task | Was | Status | Commit(s) | Verifikation |
|---|---|---|---|---|
| A0 | E2E-Render-Smoke-Test | ✅ | (Diag) | track1 (Maceo) voller Durchlauf inkl. 222 MB Export |
| A1 | Crossfade-Verdrahtung + UI-Schalter | ✅ | 7114ac4, 37dab60 | Key-Mismatch behoben; Default jetzt hart (Option B) |
| A2 | V2-Pipeline: Classify+Waveform+sub_genre | ✅ live | 763767a | track2b: mood/genre/sub_genre gesetzt, waveform 4000 samples, alle Status done |
| A3 | DB-010 Nachrüst-Migration | ✅ | ee0b1bb, 8902291 | Alt-DB-Simulation 6/6 PASS |
| B1 | SigLIP-Ausfall sichtbar | ✅ | 1a38460 | Test grün |
| B2 | Beat-Fehler-Degradierung sichtbar | ✅ | 055d3f5 | Test grün |
| B3 | GPU→CPU-Weichen (NVENC/RAFT) robust | ✅ | 83ab433 | Test grün |
| B4 | V2-Worker schreibt analysis_status | ✅ | a930468 | Test grün |
| B5 | PIPE-006 Szenen-Cut-Injektion entfernt | ✅ | e46b858 | 306 Pacing-Tests grün, Repro pb_studio.log |
| B6 | PIPE-013 Media-Panel DB-Resolve-Batch | ✅ | fb99fd3 | 9 Tests grün |
| B7 | DB-017 init_db Existenz-Guard | ✅ | 4bdd237, 93811bf | Test grün |
| B8 | B-602 Checkpoint-Kollision (projekt-relativ) | ✅ **live** | 39a6b3d | track2b: 138 Segmente statt 0; Isolations-Test 3/3 |
| B9 | B-603 Crossfade-Export-Skalierung | 📌 erstes Update | — | Deferred (Option B), Bug-File B-603 |

## Wichtigste Erkenntnisse

1. **B-602 (neu, durch A0 aufgedeckt):** Der Pipeline-Checkpoint lag CWD-global
   (`stem_cache._STORAGE_ROOT = Path("storage")`) → Projekte mit gleicher
   track_id teilten ihn → zweites Projekt übersprang alle Audio-Stages →
   Auto-Edit 0 Segmente. Fix: projekt-relativ via `APP_ROOT`. Der Live-Beweis
   (track2b) lieferte danach 138 Segmente. Ohne das Repro-Gate (R1) wäre dieser
   reale Bug nie aufgefallen.

2. **B-603 (neu, durch A1 freigelegt):** Der xfade-Filtergraph-Export war toter
   Code (crossfade wegen PIPE-001-Key-Mismatch immer 0). A1 aktivierte ihn; bei
   vielen Segmenten (137 verschachtelte xfades) liefert ffmpeg 0 Frames.
   Grundlogik intakt (4-Segment-Repro PASS) → Skalierungsproblem. User-
   Entscheidung (Option B): Default harte Cuts, Crossfade experimentell
   markiert, Fix (B9) fürs erste Update.

3. **Repro-Gate hat sich bewährt:** Zwei echte, vorher unbekannte Bugs (B-602,
   B-603) nur durch den erzwungenen Live-Durchlauf gefunden. Statische Analyse
   allein hätte beide verpasst (B-602 sah in der DB wie „done" aus; B-603 war
   toter Code).

## Ehrliche Grenzen

- `fixed` steht noch aus — der User muss die App live sichten (harte-Cut-Render,
  V2-Analyse mit Waveform/Mood im SCHNITT-Tab, Crossfade-Schalter-Verhalten).
- track2b-Export selbst wurde nur im harten Pfad (track1) bzw. 4-Segment-xfade
  bewiesen; der 138-Segment-Crossfade-Export bleibt bis B9 kaputt (bewusst,
  Option B).
- Zwei Tests (`test_storage_migration`, `test_backup_service`) failen
  umgebungsbedingt — auf unverändertem main-Stand reproduziert, unabhängig von
  diesen Änderungen.

## Nächster Schritt

Nach User-`fixed`: verbindlicher Folgeplan
`PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07` (hohe Priorität). B9 wird
mit dem ersten Update nach Release ausgerollt.
