# STAB-5 Controls #57-#63 — SetupWizard (2026-08-28)

status: target-test-pass-live-pending
findings: B-920 (low)

## Belegte Elemente

- **#57** Ollama-Modell-Checkbox (Factory `_model_row`): 2 Checkboxen,
  Defaults korrekt (gemma3:4b an, phi3:mini aus); Indikator-Klick
  aktualisiert Auswahl + Groessensumme (3.3 -> 5.6 GB).
- **#58** HF-Modell-Checkbox: **im Produkt toter Code** (`_HF_MODELS = []`,
  Finding B-920); Factory-Pfad via Monkeypatch belegt (Toggle, Auswahl,
  Summe).
- **#59** Download-`Abbrechen`: Click ruft `worker.cancel()`, sperrt sich
  selbst, Status `Breche ab…`.
- **#60** `Überspringen`: setzt Setup-Complete-Flag (isolierte QSettings)
  und akzeptiert.
- **#61** `Zurück`: auf Hardware-Seite unsichtbar; nach Weiter sichtbar,
  Click fuehrt zurueck zur Hardware-Seite.
- **#62** `Weiter →`: Hardware -> Modelle; kein Download gestartet;
  Back/Skip werden sichtbar.
- **#63** `App starten  →` (PAGE_FINISH, lazy erzeugt): einzig, ersetzt
  Weiter-Button; Click setzt Setup-Flag und akzeptiert.

## Verifikation

`tests/ui/test_stab5_setup_wizard_controls.py` (neu, 7 Tests) ->
`7 passed in 1.36s`. QSettings auf Testorganisation isoliert;
System-Check gemockt (kein Subprozess/HTTP); keine echten Downloads.
Kein Produktcodeedit.

## Findings (code-verifiziert, nicht gefixt)

- **B-920 (low):** HF-Sektion produktiv unerreichbar (`_HF_MODELS = []`);
  inkl. `_hf_cache_has`/`_download_hf` toter Code. Nebenbefund:
  `launch_btn` ohne Duplikat-Guard/Referenz, fragiler Index-Lookup.

## Grenzen

Echter First-Run-Wizard mit realem Modell-Download bleibt Live-Endgate
(B-900-Fix dort bereits real belegt).
