# STAB-5 Controls #32-#40 — ModelManagerDialog (2026-08-28)

status: target-test-pass-live-pending
findings: B-916 (medium), B-917 (low)

## Belegte Elemente

Alle 9 Buttons elementgenau mit echten QTest-Clicks, offscreen, ohne echte
Threads/Netz/Disk (Scan-Timer klassen-seitig gestubbt, Handler-Wirkung
per Recorder):

- **#32** `⟳ Aktualisieren` -> `_start_scan` genau einmal.
- **#33** Zeilen-`Löschen` (installierte Tabelle) -> `_on_delete_model`
  mit exakter (model_id, source).
- **#34** Custom-Ollama-`Herunterladen` -> `_start_download("llama3:latest",
  "ollama")`.
- **#35** Custom-HF-`Herunterladen` -> `_start_download(..., "huggingface")`.
- **#36** Empfohlen-`⬇ Herunterladen` -> `_on_pull_ollama(model_id)`
  (aktuelles Zell-Widget; deleteLater-pendente Alt-Buttons ausgeschlossen).
- **#37** Cleanup-`Analyse starten` -> `_on_cleanup_scan` (bound connect,
  Klassen-Patch vor Konstruktion noetig).
- **#38** `Alle ausgewählten löschen` -> Bestaetigungsfrage; Yes ->
  `_start_delete` mit Tabellen-Targets; No -> kein Delete (Negativpfad).
- **#39** Zeilen-`Löschen` (Cleanup-Tabelle) -> `_on_delete_model`.
- **#40** Progress-`✗` -> `svc.cancel_download(model_id)` + sichtbarer
  Statustext.

## Verifikation

`tests/ui/test_stab5_model_manager_controls.py` (neu, 10 Tests) ->
`10 passed in 1.23s`. Kein Produktcodeedit.

## Findings (code-verifiziert, nicht gefixt)

- **B-916 (medium):** `_on_delete_all_selected` uebergibt
  `display_name` statt `model_id` (Zeilen 1162-1167); Cleanup-Tabelle
  traegt keine UserRole-ID. Latenter Fehl-Delete sobald display_name
  von model_id abweicht. Zusatz: Buttontext ignoriert Selektion.
- **B-917 (low):** `_remove_progress_row` prueft
  `_progress_layout.children()` — immer leer -> "Keine aktiven
  Downloads" erscheint waehrend andere Downloads laufen. Tote Felder
  `_download_rows`/`_progress_relays`.

## Grenzen

Echter Scan/Download/Delete gegen Ollama/HF bleibt Live-Endgate.
