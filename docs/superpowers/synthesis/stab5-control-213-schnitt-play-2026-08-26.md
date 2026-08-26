# STAB-5 Controls #213/#214 — Schnitt-Preview-Transport

Datum: 2026-08-26
Bug: B-903
Status: `code-fix-pending-live-verification`

## Root Cause

`SchnittTabSchnitt` erzeugte sichtbare Play/Pause- und Stop-Buttons, verband
sie aber nicht mit der bereits vorhandenen `VideoPreviewWidget`-API. Auch
Zeitlabel und Play-Symbol konsumierten die vorhandenen Statussignale nicht.

## Code-Fix

- Play/Pause → `VideoPreviewWidget.toggle_play()`.
- Stop → `VideoPreviewWidget.stop()`.
- `position_changed` → sichtbares `mm:ss / mm:ss`-Label.
- `playback_state_changed` → Play/Pause-Symbol und Tooltip.

## Verifikation

- RED: Play-Klick blieb ohne `play_from()`-Aufruf.
- GREEN: genau ein Qt-Zieltest, `1 passed in 1.03s`.
- Test deckt Play-Klick, Zeitlabel, State-Symbol und Stop-Zustand.
- PyCompile und `git diff --check` grün.
- Parallelreview: keine Criticals; direktes gebundenes Signal/Slot-Wiring
  passt zur bestehenden Preview-Architektur.

## Offen

- Kein echter Medien-/App-Livepfad.
- Pause/Resume, Backend-Ende, Fehler und schnelle Mehrfachklicks nicht live
  geprüft.
- Kein Status `fixed`.

## Plankorrektur

Vollständige Matrixsuche zeigt #168/#169 vor #213/#214. #213 wurde wegen
trunkierter Ausgabe irrtümlich als erster unresolved-Rest gewählt. Nach diesem
bereits aktiven Fix ist #168 nächste einzige Task.
