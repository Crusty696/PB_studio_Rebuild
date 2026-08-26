# STAB-5 Control #18 — Letztes-Projekt-Aktion

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`_show_recent_projects_menu()` → `RecentProjectsManager.get_all()` liefert Projektnamen
→ echte QAction `action` mit Projektnamen als `text` und `data` → Klick triggert
`_open_recent_project`.

## Ergebnis

- Candidate-Refs waren semantisch gemischt und nicht ausreichend belegt.
- `QMenu` und `QAction` werden im echten Builderpfad erzeugt, `QMenu.exec` isoliert.
- Gefundene Aktion hat `text()==projektname`, `data()==projektpfad`, ist
  sichtbar/aktiv und Parent ist `host`.
- Popup-Position am `Tools`-Button (`_btn_recent`) belegt.
- Aktionstrigger ruft exakt `opened_paths.append` (im Stub) mit dem Projektpfad.
- Gezielter Test `1 passed in 2.35s`.
- Kein Produktcode edit.

## Offen

`QMenu.exec` bleibt isoliert; echter PBWindow-Vollstart und echter asynchroner
Pfad `_open_recent_project` → `open_project_async` fehlen. Daher nicht `fixed`.
