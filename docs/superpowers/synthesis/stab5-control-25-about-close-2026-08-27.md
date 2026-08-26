# STAB-5 Control #25 — About-Schliessen

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `AboutDialog` → sichtbarer/aktiver Accent-QPushButton `Schliessen` →
echter Mausclick → `accept` → Accepted-Signal, Accepted-Resultat und Dialog zu.

## Ergebnis

- Kein vorhandener Test belegte konkreten Close-Button-Ausloeser.
- Echter Dialog besitzt genau einen sichtbaren/aktiven Schliessen-Button.
- Button besitzt erwartetes `btn_accent`-ObjectName.
- QTest-Mausclick emittiert Accepted genau einmal, setzt Dialogresultat und
  versteckt Dialog.
- Gezielte Datei `1 passed in 2.02s`.
- Kein Produktcodeedit.

## Offen

Vollstaendiger PBWindow-/About-Menu-Livepfad fehlt. Daher nicht `fixed`.
