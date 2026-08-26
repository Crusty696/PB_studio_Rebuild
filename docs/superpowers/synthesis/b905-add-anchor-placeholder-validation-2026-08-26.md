# B-905 — Add-Anchor-Placeholder-Validierung

Datum: 2026-08-26
Status: `code-fix-pending-live-verification`

## Root Cause

Dialog akzeptierte Placeholder `-- Szene waehlen --` mit Datenwert `""`.
Accepted-Pfad erzeugte ohne Validierung ein sichtbares Anchor-TreeItem mit
leerer Szenen-ID.

## Fix

- `Hinzufuegen` initial nur bei nichtleerer Szenen-ID aktiv.
- Combo-Wechsel synchronisiert Buttonzustand in beide Richtungen.
- Defensive Accepted-Pruefung verwirft leere Szenen-ID und protokolliert sie.

## Evidence

- RED: `topLevelItemCount() == 1` statt erwartet `0`.
- GREEN nach Fix und Reviewluecken-Schluss: `2 passed in 1.27s`.
- Geprueft: Placeholder deaktiviert, Szene aktiviert, Rueckwahl deaktiviert,
  erneute Szenenwahl aktiviert, leerer programmgesteuerter Accept erzeugt nichts,
  gueltige Wahl erreicht TreeItem/Collector/Console.
- Drei gefuehrte Read-only-Reviews: PASS, keine blockierenden Findings.

## Offen

Echter PBWindow-/Projekt-DB-/Sync-Livepfad fehlt. Daher nicht `fixed`.
