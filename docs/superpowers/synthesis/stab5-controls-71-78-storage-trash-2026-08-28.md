# STAB-5 Controls #71-#78 — StorageBrowserDialog + TrashDialog (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#71** `_unused_only`-Checkbox: Click refresht mit `unused_only=True`.
- **#72** `Aktualisieren`: Click loest erneuten Service-Load aus; Summary
  zeigt Zeilen-/Bytezahl.
- **#73** `Auch Speicherdateien loeschen`: Checkbox steuert nachweislich
  `delete_storage_dirs=True` im Loeschaufruf (B-547-Vertrag).
- **#74** `Ausgewaehlte loeschen`: leere Auswahl -> sichtbare Info `Keine
  Zeile ausgewaehlt.`, kein Delete; mit Auswahl + Yes -> exakter SHA-Delete.
- **#75** Zeilenbutton `Analysen loeschen`: loescht genau die Quelle der
  Zeile nach Bestaetigung.
- **#76** Trash `Ausgewaehlte wiederherstellen`: leere Auswahl -> sichtbare
  Info; mit Auswahl -> Restore-Worker mit exakten Video-IDs + Erfolgsmeldung.
- **#77** `Papierkorb leeren`: Cancel -> kein Purge; Yes -> Purge mit
  korrekter project_id.
- **#78** Trash `Schliessen`: Accepted + hidden.

## Verifikation

`tests/ui/test_stab5_storage_trash_controls.py` (neu, 8 Tests) ->
`8 passed in 1.22s`. DB/Threads isoliert (Fake-Service/-Session, synchroner
run_worker-Fake); echte Handler-Pfade laufen. Kein Produktcodeedit.

## Testbau-Incident (behoben)

Erster Lauf hing 3 Minuten: Fake-`StorageDeleteResult` ohne Pflichtfelder ->
Produkt-Exceptpfad oeffnete echtes modales `QMessageBox.critical` offscreen.
Fix: vollstaendiger Fake + critical-Patch als Sicherheitsnetz, das jeden
unerwarteten Fehlerdialog als Assertion sichtbar macht.

## Grenzen

Echte DB-/Datei-Loeschungen und App-Livepfad bleiben Endgate.
