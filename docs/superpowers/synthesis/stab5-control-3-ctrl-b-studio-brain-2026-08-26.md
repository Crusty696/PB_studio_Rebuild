# STAB-5 Control #3 — Ctrl+B Studio Brain

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`Ctrl+B` → `QShortcut` im `PBWindow` → `PBWindow._open_studio_brain()` →
`StudioBrainWindow.instance()` → Signalverdrahtung →
`show()` / `raise_()` / `activateWindow()`.

## Ergebnis

- Statischer Produktpfad vollständig verdrahtet.
- Ein fokussierter offscreen Qt-Keytest sendet Ctrl+B zweimal an das Hostfenster
  und verwendet dabei den echten `PBWindow._open_studio_brain`-Handler.
- Derselbe Fake-Singleton wird zweimal abgerufen; Fenster wird je Aufruf gezeigt,
  angehoben und aktiviert.
- Timeline- und Run-Signal bleiben trotz zweier Aufrufe jeweils genau einmal
  verbunden.
- Ergebnis: `1 passed in 5.73s`.
- Drei geführte Read-only-Prüfer fanden keinen belegten Produktdefekt.
- Kein Produktcode geändert.

## Offen

- Kein realer PBWindow-App-Lauf mit sichtbarem Studio-Brain-Fenster.
- Windows-Fokusverhalten, minimiertes Fenster und echter Brain-/GPU-Inhalt sind
  durch diesen Kontrolltest nicht belegt.
- Lifecycle-Hardening ohne reproduzierten Defekt wurde nicht umgesetzt.
