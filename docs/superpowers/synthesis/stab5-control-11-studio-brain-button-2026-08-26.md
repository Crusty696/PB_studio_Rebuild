# STAB-5 Control #11 — Studio-Brain-Button

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter sichtbarer `Brain`-Button → echter QTest-Mausclick → lokaler
Produkt-Connect → `PBWindow._open_studio_brain()` → Singletonzugriff →
Signalsync → show/raise/activate.

## Ergebnis

- Control-#3-Evidence belegte bereits denselben Handler per Ctrl+B, nicht Button.
- Neuer Test nutzt echten Top-Bar-Builder; kein manuell nachgebautes Wiring.
- Zwei Clicks rufen Singleton zweimal auf und dasselbe Fenster je zweimal auf.
- Timeline-/Run-Signale bleiben nach Wiederaufruf je exakt einmal verbunden.
- Gezielter Test: `1 passed in 11.23s`.
- Drei gefuehrte Read-only-Reviews PASS; kein Produktcode geändert.

## Offen

StudioBrainWindow selbst ist Testdouble; realer PBWindow-/Brain-Inhalt-/GPU-
Livepfad fehlt. Daher nicht `fixed`.
