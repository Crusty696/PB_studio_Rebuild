# Zwischen-Synthese: NEUBAU-VOLLINTEGRATION — Meilenstein M1 (Paket 2) komplett

- **Plan:** `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`
- **Branch/Worktree:** `claude/NEUBAU-VOLLINTEGRATION-2026-07-07` in `.worktrees/vollintegration` (Parallel-Betrieb zum Audit-Fixplan im Haupt-Worktree, User-Gate-Aufhebung 2026-07-07)
- **Stand:** 2026-07-08, Commits `b121686…b1e30b6` (11), alle auf origin
- **Status:** M1 code-complete-live-pending (Live-GUI-Sichtung nach Merge)

## Erledigte Tasks

| Task | Commit | Inhalt | Verify |
|---|---|---|---|
| T2.2 audio.v2_default-UI (USE-012) | 30cbc4e | Settings-Tab „Analyse", erster set_nested-Schreiber | 7 Tests |
| T2.1 LLM-Pacing schaltbar (USE-007) | 2c5afde | 2 Checkboxen im Pacing-Panel, Store-Persistenz, Ollama-Gate, Durchreichung in AdvancedPacingSettings | 9 Tests |
| T2.3 Timeline-Snapshots (USE-009, DB-005/016/019) | b7f2ce6 | Auto-Snapshot bei jedem Apply, Restore-Menue in Timeline-Shell (mit Auto-Backup), Versions-Lock, Dicts statt detached ORM, Retention 20 | 8 Tests |
| T2.4 SetupWizard First-Run (WIRE-001/DEAD-002) | a95154b | `_maybe_run_setup_wizard` vor PBWindow, QSettings-Gate, fehlertolerant, B-563 unberuehrt | 7 Tests |
| T2.5.1 cut_snapper + PIPE-016 | cca0669 | Onset-Feinsnap ±50 ms nach finalize; Onset-Analyse ohne 1800s-Cap (chunked) | Headless echte Daten: 99/114 gesnappt, Beat-Sync 100 % |
| T2.5.2 Drop-Burst/Phrase/Coherence | 4188292 | Drop-Burst 3×/800 ms + 4-Bar-Hold; Phrase-Boundary-Penalty; Coherence-Term; Shadowing-Bug `beat_idx` gefixt; `apply_bpm_adaptation` bewusst NICHT (redundant zu SECTION_PACING_MAP) | Headless: 134 Cuts, 100 % Beat-oder-Onset |
| T2.5.3 Vocal-on-Hold (FR-S1-2) | bf7e353 | Section-Stem-Aggregation aus per-Beat-Demucs-Energien, Mindestdauer ×2 in Vocal-Sections, dominant_stem pro Section | 19 Tests |
| T2.5.4 Slice-1-Scorer-Terme | 582d25a | Kurven-Energy, Vektor-Mood, stem_class-Bonus (Daten-Gates + Fallbacks); shot_centroids.py (SigLIP-Text); Golden-Baseline regeneriert | 34 Tests |
| T2.5.5 shot_type_classifier (FR-S2-1) | f250708 | Run-weite Klassifikation, Embedding+Konfidenzen in ClipFeatures (loest Cycle-12-deferred B-371) | 36 Tests |
| T2.5.6 ab_runner-UI (FR-S4-5) | b1e30b6 | ABCompareDialog + Button „A/B-Gewichte testen" im Pacing-Panel | 14 Tests |

**Slice-1-Bilanz:** 13 von 16 Modulen produktiv verdrahtet; `rl_memory_v2`/`rl_policy`/`variety_memory` folgen planmaessig in T1.4 (M2). `apply_bpm_adaptation` dokumentiert nicht verdrahtet (Begruendung oben).

## Offene Punkte / naechste Schritte

1. **M2 (Paket 1, T1.1–T1.6):** Vorher Haupt-Branch einmergen — Audit-Fixplan-Voraussetzungen (B1–B4 committed, A2 lief zuletzt, A0-Status pruefen). Paket-1-Default-AN-Abnahme erst nach A2-Merge.
2. **M3 (Paket 3, DAG-Engine).**
3. **Abschluss:** Auto-Merge in `codex/OTK-021-…` nach gruenem Gesamt-Test (User-Auftrag, in ACTIVE_PLAN dieses Worktrees verankert). Bekannte Merge-Punkte: TRACK_HEIGHT 140 (Haupt gewinnt), finalize-Tail-Regel, Scorer-Gewichts-Nacharbeiten des Haupt-Branches.
4. Kurven-Fuellung (`at_rms_curve`/`motion_curve`) fuer den Kurven-Energy-Term folgt mit T1.2-Rollout; Fallback aktiv + getestet.
