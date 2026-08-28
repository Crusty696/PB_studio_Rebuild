# STAB-5 Controls #48-#56 — SettingsDialog (2026-08-28)

status: target-test-pass-live-pending
findings: B-918 (low), B-919 (low)

## Belegte Elemente

Alle 9 Widgets elementgenau mit echten QTest-Interaktionen, vollstaendig
isoliert (Modul-lokale Bindings gepatcht — keine Host-settings.json-Writes,
kein Ollama-HTTP, keine QThreads, keine modalen Sub-Dialoge):

- **#48** `Bearbeiten` (Shortcuts): KeyCapture-Ergebnis F5 landet in
  `_pending` + Tabellenzelle; kein Singleton-Write vor OK.
- **#49** `Alle zurücksetzen`: `_pending` = Defaults aller ACTIONS, kein Save.
- **#50** Checkbox `Ollama als LLM-Backend nutzen`: Click schaltet URL-Feld,
  Test-, Modell-, Refresh-Widgets ab und wieder an.
- **#51** `Verbindung testen`: Worker mit exakter URL, Status
  `Teste Verbindung...`, Button gesperrt; Payload-Ende fuellt Modelle,
  entsperrt, nullt Thread-Referenzen.
- **#52** Modell-Combo (editierbar): getippter Name `phi3:mini` erreicht
  `save_ollama_settings` ueber OK-Pfad inkl. Offline-toleranter Validierung.
- **#53** `↻`: delegiert nachweislich an den Test-Handler mit aktueller URL.
- **#54** `⊞ Modell-Manager öffnen`: oeffnet ModelManagerDialog(parent, url)
  modal (Fake-exec-Beleg).
- **#55** `Storage-Browser`: oeffnet StorageBrowserDialog(parent) modal.
- **#56** Checkbox `Audio-Analyse V2 als Standard`: Click + OK schreibt
  `audio.v2_default=False` in den Store; Shortcut-Apply lief genau einmal.

## Verifikation

`tests/ui/test_stab5_settings_dialog_controls.py` (neu, 9 Tests) ->
`9 passed in 1.29s`. Kein Produktcodeedit.

## Findings (code-verifiziert, nicht gefixt)

- **B-918 (low):** Refresh bleibt waehrend laufendem Test aktiv;
  zweiter Klick ueberschreibt `_test_thread`/`_test_worker` — Referenz
  auf laufenden Thread verloren (564-577, 605-606).
- **B-919 (low):** `_populate_models` verwirft manuell eingetippten
  Modellnamen kommentarlos (608-616). Nebenbefund: `Bearbeiten` ohne
  Selektion ist stiller No-Op.
- Test-seitige Beobachtung: `tests/ui/test_settings_ollama_async_save.py`
  patcht `services.settings_store.*` — wirkungslos, weil der Dialog
  Modul-lokale Bindings haelt; dessen `_Store`-Fake ist toter Code.

## Grenzen

Echter Ollama-Verbindungstest, echte settings.json-Persistenz und
PBWindow-Livepfad bleiben Endgate.
