---
title: STAB-3 Negativkontrolle ohne Feedback
date: 2026-08-24
status: agent-complete
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
controlled_runs: [8, 9]
---

# STAB-3 Negativkontrolle ohne Feedback

- Direkter Run 6/7 war rot: 95/101 Szenen und 101/101 Scores verschieden.
- Root Cause B-887: Auto-Edit persistiert bewusst Playback-Offsets; Run 7
  hatte dadurch nicht denselben Input wie Run 6. Kein Brain-/RNG-/Feedback-
  Defekt.
- Produktfunktion F-001 blieb unveraendert. Fuer echtes Kontrollpaar wurde
  kompletter Offsetzustand vor Run 8 gebunden und vor Run 9 exakt restauriert.
- Run 8/9 sind kanonisch identisch: 101 Decisions, Timeline, Brain-Sync-Cuts
  und resultierende Playback-Offsets.
- Je Lauf 101/101 Brain V3, Rang 1 aus 109 Kandidaten und exakt 18 Achsen.
- Patterns/Feedback 0; Settings und `weights.db` unveraendert; DB-/State-
  quick_check ok; neue Errorzeilen 0.
- Echtes Fenster nach Run 9: Waveform, Marker, 101 Thumbnail-Segmente,
  Cutliste, 337 s und Taskstatus `Fertig` sichtbar.
- Separat erfasst: B-888 offenes, noch nicht reproduziertes Risiko einer
  nicht kanonischen Kandidaten-Tie-Break-Reihenfolge.

Evidence: `tests/qa_artifacts/stab3_negative_control_20260824.json`.

Naechste einzige Task: `STAB-3 / Gezieltes positives/negatives Feedback,
Flush, kompletter App-Neustart`.
