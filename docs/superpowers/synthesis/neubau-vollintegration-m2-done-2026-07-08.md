# NEUBAU-VOLLINTEGRATION — M2 (Paket 1: Studio-Brain live) code-complete

- **Plan:** PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07
- **Datum:** 2026-07-08
- **Worktree/Branch:** `.worktrees/vollintegration` / `claude/NEUBAU-VOLLINTEGRATION-2026-07-07`
- **Status:** code-complete-live-pending — Live-Verify der Paket-1-Abnahme
  erst nach A2-Merge vom Haupt-Branch (Default bleibt AUS).

## Tasks

| Task | Inhalt | Commit |
|---|---|---|
| T1.1 | Studio-Brain als persistentes Setting (`pacing.use_studio_brain`, Checkbox, Env-Var bleibt Override) | 2222f90 |
| T1.2 | Brain-V3-Reranker angekoppelt (`use_brain_v3=True`, `brain_v3_min_confidence` aus Settings) | 20255b8 |
| T1.3 | SteerOverrideQueue-Consumer: Boost -> STEER_BOOST_BONUS 0.5 (Stage-4 + Brain-V3-final), Exclude -> harter Ausschluss (never-empty-cut), Drain nach Lauf. Pins bewusst NICHT (UI-in-memory, P11+) | 8d7a538 |
| T1.5 | Lernschleife geschlossen: `services/pacing/pattern_lookup.py` (LearnedPatternLookup) am Produkt-Scorer — w_memory-Term lebt | 3182f43 |
| T1.4 | RL-Stack v2 an Feedback: FeedbackService -> RLPacingMemoryV2-Singleton (ohne DB-Writer = kein Doppel-Write) + WeightStore via BrainV3Service.feedback (accept->fits, reject->no_match) | 94e95a4 |
| T1.6 | Feedback-Bestaetigung sichtbar; WIRE-004/008/009/010/012 verdrahtet; WIRE-011 (`stats_refreshed`) entfernt | 8f405c6 |

## Nebenfixe (T2.5.4-Altlasten, in T1.5/T1.4 mitgefixt)

- `stem_class` fehlte in `CANONICAL_TERM_KEYS` (scorer.py).
- `w_stem_class` fehlte in `config/pacing_weights/default.yaml`.

## Offene Live-Verifies (Paket-1-Abnahme, nach A2-Merge)

1. Reranker-A/B-Lauf (an/aus) unterscheidet sich; VRAM GTX 1060 stabil.
2. Exclude im Steer-Tab -> Clip fehlt im Auto-Edit; Boost -> messbar haeufiger.
3. End-to-End-Lernbeweis: Feedback -> memory_updater -> Pattern -> naechster Lauf entscheidet anders.
4. WeightStore-Diff vor/nach A/R-Verdict in der App.
5. `fixed` setzt nur der User.

## Testlage

Alle Task-Suites + Regression gruen (u.a. 108er-Lauf pacing+memory+feedback+golden,
51+23 UI-Tests, Golden-Snapshot nach Scorer-Erweiterung stabil).
