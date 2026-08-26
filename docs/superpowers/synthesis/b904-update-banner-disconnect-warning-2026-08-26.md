# B-904 — Update-Banner Disconnect-RuntimeWarning

Datum: 2026-08-26
Status: `code-fix-pending-live-verification`

## Root Cause

`PBWindow._on_update_available()` rief beim ersten Update-Signal pauschal
`clicked.disconnect()` auf, obwohl noch keine Verbindung existierte. PySide6
erzeugte dadurch `RuntimeWarning: Failed to disconnect (None) ...`.

## Code-Fix

- Download-Slot wird am Fenster gespeichert.
- Nur der zuvor gespeicherte eigene Slot wird gezielt getrennt.
- Erstverbindung führt keinen Disconnect aus.
- Fremde mögliche Signal-Consumer bleiben unberührt.

## Verifikation

- Fokussierter Qt-Zieltest: `1 passed in 4.56s`, keine Warning.
- Zwei Update-Signale + echter Click öffnen nur neueste URL genau einmal.
- PyCompile und Diffcheck folgen im Abschlussgate.
- Drei geführte Read-only-Reviews: PASS, kein Blocker.

## Offen

- Kein echter PBWindow-/Release-/Browser-Livepfad; daher nicht `fixed`.
- Späterer leerer URL-Folgeaufruf ist im aktuellen einmaligen Workerpfad nicht
  belegt und wurde nicht außerhalb Scope mitverändert.
