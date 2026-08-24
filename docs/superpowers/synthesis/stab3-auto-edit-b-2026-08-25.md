# STAB-3 Auto-Edit B — 2026-08-25

status: agent-complete-await-user-marker
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
task: STAB-3 / Auto-Edit B mit identischen Eingaben; erklaerbare Aenderung nur adressierter Beitraege und Kandidatenrangfolge beweisen

## Ergebnis

Auto-Edit B wurde mit denselben 112 restaurierten Playback-Offsets, Seed 42,
identischen 101 Input-Kontexten und identischer Kandidatenreihenfolge gegen
Run 9 ausgefuehrt. Erstlauf Run 10 deckte B-892 auf: positives 1/1-Feedback
senkte den Memory-Wert. Nach Root-Cause-Fix bestaetigte Run 11 korrekte
Richtung fuer positives und negatives Feedback.

## Belege

- 101 Decisions/Cuts; 18 Brain-Achsen; 101/101 Brain V3.
- Timeline: 101 Video-, 1 Audioeintrag; 337.137 s; keine Gaps/Overlaps;
  101 verschiedene Medien, maximale Nutzung 1.
- Negatives Ziel Scene 127/Clip 106, Sequence 5:
  - Memory `0.1 -> 0.0793456709`.
  - Rang `1/17 -> 4/17`; Ziel nicht mehr gewaehlt.
- Positives Ziel Scene 32/Clip 19, Sequence 31:
  - Memory `0.1 -> 0.1206543292`.
  - Brainfinal `0.7118881634 -> 0.7263461964`.
  - Softscore `0.8470252301 -> 0.8676795634`.
- `weights.db` blieb unveraendert; alle 138 Zeilen lagen unter der
  Mindeststichprobe. Direkter Lernbeleg dieses Laufs gilt deshalb nur fuer
  Pattern Memory, nicht fuer WeightStore-Achsen.
- Run 10 und Run 11 hatten identische Clipauswahl. B-892 korrigierte
  Bewertungsrichtung; dieser Datensatz beweist keine dadurch geaenderte
  Endauswahl fuer das positive Ziel (Pool 1/1).
- DB-Quickchecks gruen; Beleg-JSON erfolgreich geparst.

## Fix

- B-892 `agent-fixed-await-user`, Commit `7ebdaf2`.
- Memory- und genre/key/spectral-Priors verwenden neutral-zentrierten
  Wilson-Preference-Score. Aggregator-Konfidenz bleibt konservative
  Wilson-Untergrenze.
- Zwei direkte Richtungs-Tests und drei Nachbarregressionen gruen.

## Separat offene Findings

- B-893: WeightStore Motion/Pace-Kontextschluessel stimmen nicht ueberein.
- B-894: Achsen ohne verwertbares Signal erhalten Credit.
- B-895: WeightStore-Skala springt abrupt ab zehn Samples.

Diese Findings wurden dokumentiert, nicht in B-892 mitgefixt.

## Evidenzpfade

- `tests/qa_artifacts/stab3_auto_edit_b_20260825.json`
- `tests/qa_artifacts/stab3_auto_edit_b_run10_failed_direction_20260825.png`
- `tests/qa_artifacts/stab3_auto_edit_b_postfix_run11_20260825.png`
- `tests/qa_artifacts/stab3_auto_edit_b_pre_restore_20260825.db`
- `tests/qa_artifacts/stab3_auto_edit_b_run10_pre_retry.db`

## Statusgrenze

Agentseitiger Live-Beleg abgeschlossen. Kein User-`fixed`- oder
STAB-3-Phasenmarker gesetzt. Naechste Plan-Task:
`STAB-3 / Tool- und Non-Tool-LLM-Pfade muessen Recall/Stats/Explain/Learn erhalten`.
LLM-AN-Liveausfuehrung bleibt wegen B-867/Modellwahl user-blockiert.
