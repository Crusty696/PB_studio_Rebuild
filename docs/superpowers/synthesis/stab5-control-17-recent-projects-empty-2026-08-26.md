# STAB-5 Control #17 — Letzte-Projekte-Leerzustand

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`_show_recent_projects_menu()` → leerer RecentProjectsManager → echte QAction
`(Keine letzten Projekte)` → sichtbar, deaktiviert → QMenu-Popup an Unterkante
des Tools-Buttons.

## Ergebnis

- Candidate-Refs waren semantisch fremd.
- Echte QMenu/QAction verwendet; nur blockierendes `QMenu.exec` isoliert.
- Genau eine Aktion mit erwartetem Text, Window-Parent und `enabled=False`.
- Aktion bleibt sichtbar; Popup-Position entspricht `_btn_recent.bottomLeft()`.
- Gezielter Test `1 passed in 1.35s`.
- Kein Produktcode geaendert.

## Offen

Echtes modales Popup im PBWindow fehlt. Daher nicht `fixed`.
