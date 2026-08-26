# STAB-5 Control #19 — Letzte-Projekte-Liste leeren

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

`_show_recent_projects_menu()` → gefuellter RecentProjectsManager → Separator →
echte QAction `Liste leeren` → `_clear_recent_projects()` →
`RecentProjectsManager.clear()` + Statusmeldung.

## Ergebnis

- Candidate-Refs waren semantisch fremd und kein Elementbeleg.
- Echter QMenu/QAction-/StatusBar-Pfad; nur blockierendes `QMenu.exec` isoliert.
- Clear-Aktion ist letzter Eintrag nach Projektaktion und Separator, sichtbar,
  aktiv und besitzt Window-Parent.
- Popup-Position am Tools-Button belegt.
- Trigger leert Store exakt einmal und zeigt `Letzte Projekte geleert.`.
- Gezielter Test `1 passed in 12.26s`.
- Kein Produktcodeedit.

## Offen

Echtes modales PBWindow-Popup und reale Settings-Persistenz im Vollstart fehlen.
Daher nicht `fixed`.
