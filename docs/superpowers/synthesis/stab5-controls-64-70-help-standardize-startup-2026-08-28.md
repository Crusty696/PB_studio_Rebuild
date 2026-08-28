# STAB-5 Controls #64-#70 — ShortcutHelp/Standardize/StartupCheck (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#64** `ShortcutHelpDialog btn_close / Schließen`: einzig/sichtbar/aktiv;
  Click akzeptiert und versteckt den Dialog.
- **#65-#67** `StandardizeVideosDialog convert_resolution/convert_fps/
  convert_format`: sichtbar/aktiv, korrekte Itemzahl (4/5/5); Auswahl speist
  exakt den `selected()`-Vertrag fuer `ConvertController._run_standardize`
  (belegt mit 4K/24fps/Copy).
- **#68** `StartupCheckDialog btn_quit / Beenden`: erscheint nur im
  Fehlerzweig; Click rejected (App-Exit-Vertrag von
  `maybe_show_startup_dialog`).
- **#69** `btn_start / Trotzdem starten (degradierter Modus)`: Fehlerzweig;
  Click akzeptiert.
- **#70** `btn_ok / Weiter`: erscheint nur ohne Fehler (Warnungszweig);
  Fehler-Buttons existieren dann nachweislich nicht; Click akzeptiert.

## Verifikation

`tests/ui/test_stab5_help_standardize_startup_controls.py` (neu, 5 Tests) ->
`5 passed in 0.92s`. Kein Produktcodeedit. StartupCheckDialog mit echtem
`SystemStatus`-Dataclass beider Zweige konstruiert.

## Grenzen

Echter App-Start mit realen Systemcheck-Ergebnissen und echter
Konvertierungslauf bleiben Live-Endgate.
