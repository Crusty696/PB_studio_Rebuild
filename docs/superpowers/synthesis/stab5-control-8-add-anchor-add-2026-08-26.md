# STAB-5 Control #8 — Add-Anchor-Hinzufuegen

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter `Hinzufuegen`-Button → echter `QPushButton.click()` →
`clicked` → `dialog.accept()` → Accepted-Consumer → TreeItem/UserRole →
Anchor-Collector und Console.

## Evidence-Abgleich

- Fruehere Candidate-Refs prueften Timeline-Checkbox bzw. allgemeine Qt-Fixes,
  nicht den Add-Anchor-Button.
- Test nutzt echten Button und echte Signalverbindung; nur modaler Eventloop und
  DB-Rand sind isoliert.

## Ergebnis

- Button ist beim Placeholder deaktiviert und nach echter Szenenwahl aktiv.
- Echter Click setzt Dialogresultat auf Accepted; ohne Wiring scheitert Assert.
- Nach Rueckgabe des echten Resultats erreicht Szenen-ID `scene-42` TreeItem,
  UserRole, Collector und Console.
- Gezielter Test: `1 passed in 1.25s`.
- Drei gefuehrte Read-only-Reviews: PASS, keine blockierenden Findings.
- Kein Produktcode geändert.

## Offen

Kein echter Modal-Eventloop, PBWindow-/Projekt-DB-/Sync-Livepfad. Daher nicht
`fixed`.
