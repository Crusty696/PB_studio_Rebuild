# STAB-5 Control #9 — Add-Anchor-Abbrechen

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter `Abbrechen`-Button → echter `QPushButton.click()` →
`clicked` → `dialog.reject()` → Rejected-Rueckgabe → kein Accepted-Consumer.

## Evidence-Abgleich

- Fruehere Candidate-Refs prueften Timeline-Checkbox bzw. allgemeine Qt-Fixes,
  nicht den Add-Anchor-Cancel-Button.
- Dialog wird vor Click bewusst auf Accepted gesetzt. Ohne Reject-Wiring wuerde
  Test am Rejected-Assert scheitern.

## Ergebnis

- Vor Cancel liegen gueltige Szene `scene-42` und Zeit `12.5` vor.
- Echter Cancel-Click setzt Resultat von Accepted auf Rejected.
- Danach entstehen kein TreeItem, keine Collector-Daten und kein Consoletext.
- Erster Review fand Maskierungsrisiko durch leere Placeholder-ID; Test mit
  gueltigen Nutzdaten geschaerft, Nachreview PASS.
- Gezielter Test: `1 passed in 1.29s`.
- Kein Produktcode geändert.

## Offen

Kein echter Modal-Eventloop, Maus-Hitbox-/PBWindow-/Projekt-Livepfad. Daher
nicht `fixed`.
