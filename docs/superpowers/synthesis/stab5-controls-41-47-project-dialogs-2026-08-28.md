# STAB-5 Controls #41-#47 — NewProjectDialog/OpenProjectDialog (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#41** `NewProjectDialog btn_browse / ...`: einzig/sichtbar/aktiv; Click
  ruft Ordnerauswahl (isoliert) und setzt `path_input` auf gewaehlten Ordner.
- **#42** `resolution_combo`: sichtbar/aktiv, 6 Eintraege; Auswahl Index 1
  liefert `3840x2160` in `get_values()["resolution"]`.
- **#43** `NewProjectDialog btn_cancel / Abbrechen`: Click rejected + hides.
- **#44** `btn_ok / Erstellen`: leerer Name → genau eine sichtbare Warnung
  `Bitte einen Projektnamen eingeben.`, Dialog bleibt offen; mit Name+Pfad →
  Accepted, `get_values()` liefert `path/name`-Vertrag.
- **#45** `OpenProjectDialog btn_browse / ...`: Click setzt Pfad und
  `_check_path` meldet `pb_studio.db (SQLite) gefunden` bei echtem
  SQLite-Header (B-138-Pfad real ausgefuehrt).
- **#46** `OpenProjectDialog btn_cancel / Abbrechen`: Click rejected + hides.
- **#47** `btn_ok / Oeffnen`: Text-Datei als pb_studio.db → sichtbare Warnung
  `keine gueltige SQLite-Datenbank` (B-352-Pfad real), Dialog bleibt offen;
  echte SQLite-Datei → Accepted, `get_path()` korrekt.

## Verifikation

`tests/ui/test_stab5_project_dialog_controls.py` (neu, 7 Tests) →
`7 passed in 0.97s`. Kein Produktcodeedit. Hinweis: 0-Byte-SQLite-Connect
schreibt keinen Header — Fixture erzeugt echte Tabelle.

## Grenzen

Echter PBWindow-Menuepfad (Projekt neu/oeffnen inkl. realer Projektanlage)
bleibt Live-Endgate.
