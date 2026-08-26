# STAB-5 Control #1 — F1-Shortcut-Hilfe

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`F1` → `QShortcut` im `PBWindow` →
`ProjectManagementController._show_shortcut_help()` →
`ShortcutHelpDialog(parent=PBWindow).exec()`.

## Ergebnis

- Statischer Produktpfad vollständig verdrahtet.
- QShortcut-Lifetime durch Parent `PBWindow` gesichert.
- Ein gezielter Qt-Test sendet echten F1-Keyevent und belegt genau einen
  Handler-/Dialogaufruf mit richtigem Parent.
- Ergebnis: `1 passed in 2.10s`.
- Drei parallele Read-only-Prüfer fanden keinen belegten Produktdefekt.
- Kein Produktcode geändert.

## Offen

- Kein realer PBWindow-App-Lauf mit sichtbar geöffnetem Dialog.
- Ctrl+? (#2) bleibt eigener nächster Elementbeleg.
- Vorschläge zu gespeicherter Shortcut-Referenz/AutoRepeat waren Hardening ohne
  reproduzierten Defekt und wurden nicht umgesetzt.
