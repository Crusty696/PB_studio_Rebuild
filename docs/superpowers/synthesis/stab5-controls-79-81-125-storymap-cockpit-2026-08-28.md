# STAB-5 Controls #79-#81 + #125 — StoryMap-Header + GraphCockpit (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#79** `Als PNG exportieren`: einzig/sichtbar/aktiv; Click emittiert
  exakt `exportPngClicked` (produktiv mit `_on_export_png_clicked` verbunden,
  story_map_dialog.py:426).
- **#80** `Als SVG exportieren`: Click emittiert exakt `exportSvgClicked`.
- **#81** `Schließen`: Click emittiert `closeClicked` (produktiv mit
  `close` verbunden, Zeile 428); Header-Titel traegt Run-ID.
- **#125** GraphCockpit `Aktualisieren`: bound connect -> Klassen-Patch;
  Konstruktor ruft `_refresh_html` einmal, Click genau ein weiteres Mal.
  QtWebEngine/-Channel als nicht verfuegbar isoliert (Fallback-Pfad),
  Fake-ViewModel ohne DB.

## Verifikation

`tests/ui/test_stab5_storymap_cockpit_controls.py` (neu, 4 Tests) ->
`4 passed in 3.06s`. Kein Produktcodeedit.

## Grenzen

Echter Story-Map-Datenpfad (BrainService), echter PNG-/SVG-Export und
WebEngine-Graph bleiben Live-Endgate.
