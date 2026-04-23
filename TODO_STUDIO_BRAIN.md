# TODO: Studio Brain Implementation

## P0 — Pre-flight
- [x] **T0.1a** — Build `scripts/build_test_fixture.py`
- [x] **T0.1b** — Run the script on the user's real material
- [x] **T0.2** — Add new dependencies (`umap-learn`, `pyqtgraph`, `networkx`)
- [x] **T0.3** — Reserve storage subdirs (`storage/backups/`, `storage/enricher/`)

## P1 — DB schema + Alembic migrations
- [x] **T1.1** — Migration A: struct_* layer
- [x] **T1.2** — Migration B: mem_* layer
- [x] **T1.3** — Migration C: AnalysisStatus + AIPacingMemory coexistence
- [x] **T1.4** — Integration test: full migration roundtrip

## P2 — WilsonLowerBound helper
- [x] **T2.1** — Implementation + TDD tests

## P3 — Enrichment deep modules
- [x] **T3.1** — RoleClassifier
- [x] **T3.2** — MoodAnchorMatcher + anchor generation
- [x] **T3.3** — StyleBucketClusterer
- [x] **T3.4** — CompatGraphBuilder

## P4 — Enrichment Worker + AnalysisStatus hookup
- [x] **T4.1** — StructureEnrichmentWorker
- [x] **T4.2** — Trigger hookup to existing pipeline

## P5 — Onset chunking fix (DJ-mix support)
- [x] **T5.1** — test_onset_chunked_boundary (release-gate)
- [x] **T5.2** — Implement per-segment chunking

## P6 — Pacing pipeline (4-stage)
- [x] **T6.1** — VariationsBudget
- [x] **T6.2** — PacingScorer (all 13 terms)
- [x] **T6.3** — Weights & rules YAMLs
- [x] **T6.4** — 4-stage agent pipeline integration
- [x] **T6.5** — LLM-layer refactor (separate sub-PR)

## P7 — Memory layer
- [x] **T7.1** — DecisionRecorder
- [x] **T7.2** — PatternAggregator
- [x] **T7.3** — MemoryUpdaterWorker
- [x] **T7.4** — Integration: pacing_with_memory

## P8 — Feedback UI in Timeline
- [x] **T8.1** — Shortcut handler + async persist

## P9 — Backup Service
- [x] **T9.1** — Scheduled + triggered backups

## P10 — StudioBrainWindow + Structure Tab
- [x] **T10.1** — Window shell + Brain-Service
- [x] **T10.2** — Structure tab (Grid, Graph, Inspector, Stats)

## P11 — Memory / Audit / Steer tabs
- [x] **T11.1** — Memory tab
- [x] **T11.2** — Audit tab
- [x] **T11.3** — Steer tab

## P12 — Story-Map Dialog
- [x] **P12** — implementation + trigger

## P13 — DJ-mix 3h integration test
- [x] **P13** — Synthetic 3h test + memory profile

## P14 — Golden-Run-Snapshot test
- [x] **P14** — Baseline generation + regression test

## P15 — Performance regression test
- [x] **P15** — Latency and enrichment throughput tests

## P16 — Release gate & finalisation
- [x] **P16** — Final checklist & release-ready marker
