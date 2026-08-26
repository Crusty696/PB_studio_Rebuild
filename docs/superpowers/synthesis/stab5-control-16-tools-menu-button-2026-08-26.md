# STAB-5 Control #16 — Tools-Menuebutton

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter sichtbarer `Tools`-QPushButton → echter Mausclick →
gebundenes produktives QMenu wird sichtbar.

## Ergebnis

- Candidate-Refs prueften fremdes Statuspanel/Regenerate-Verhalten.
- Echter WorkspaceSetupController baut Button und vollstaendiges QMenu.
- Genau ein sichtbarer/aktiver `Tools`-Button; `_btn_recent` zeigt auf ihn.
- Gebundenes Menu beginnt mit Tasks-, Log- und KI-Chat-Aktion.
- Echter Mausclick oeffnet das Menu sichtbar.
- Gezielter Test `1 passed in 2.15s`.
- Kein Produktcode geaendert.

## Offen

PBWindow-Vollstart und manuelle Auswahl aller Menueaktionen fehlen. Daher nicht
`fixed`.
