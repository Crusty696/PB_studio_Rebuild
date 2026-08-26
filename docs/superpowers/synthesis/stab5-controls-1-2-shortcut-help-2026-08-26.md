# STAB-5 Controls #1/#2 — Shortcut-Hilfe

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`F1` → `QShortcut` im `PBWindow` →
`ProjectManagementController._show_shortcut_help()` →
`ShortcutHelpDialog(parent=PBWindow).exec()`.

## Ergebnis

- Statischer Produktpfad vollständig verdrahtet.
- QShortcut-Lifetime durch Parent `PBWindow` gesichert.
- Zwei gezielte Qt-Parameterfälle senden echte F1- und Ctrl+Question-Keyevents
  und belegen je genau einen Handler-/Dialogaufruf mit richtigem Parent.
- Ergebnisse: F1 `1 passed in 2.10s`; Ctrl+? `1 passed in 1.19s`.
- Drei parallele Read-only-Prüfer fanden keinen belegten Produktdefekt.
- Kein Produktcode geändert.

## Offen

- Kein realer PBWindow-App-Lauf mit sichtbar geöffnetem Dialog.
- Echter PBWindow-Livepfad für beide Shortcuts bleibt offen.
- Vorschläge zu gespeicherter Shortcut-Referenz/AutoRepeat waren Hardening ohne
  reproduzierten Defekt und wurden nicht umgesetzt.
