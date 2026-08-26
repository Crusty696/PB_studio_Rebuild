# STAB-5 Control #4 — Update-Banner Download

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`VersionCheckWorker.update_available` → `PBWindow._on_update_available()` →
Banner + Download-Button sichtbar → Click → `webbrowser.open(download_url)`.

## Ergebnis

- Initialzustand von Banner und Download-Button ist hidden.
- Zwei aufeinanderfolgende Update-Signale ersetzen die Click-Verbindung.
- Echter Qt-Button-Click öffnet genau die neueste übergebene URL.
- Fokussierter Zieltest: `1 passed in 4.85s`.
- Drei geführte Read-only-Prüfer bestätigen funktionsfähigen Controlpfad.
- Kein Produktcode geändert.

## Offen

- Kein echter PBWindow-/Timer-/Worker-/Browser-Livepfad.
- Kanonisches GitHub-Repo ist erreichbar, aber `/releases/latest` liefert
  aktuell 404, weil kein Release existiert. Das geplante STAB-6 Release-Gate
  muss Release-Artefakt und echten Updatepfad belegen.
- B-904: erster pauschaler Signal-Disconnect erzeugt eine reproduzierbare
  RuntimeWarning. Funktion bleibt erhalten; separater enger Fix folgt.
