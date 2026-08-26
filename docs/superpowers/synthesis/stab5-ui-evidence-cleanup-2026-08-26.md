# STAB-5 UI-Evidenzbereinigung

Datum: 2026-08-26
Status: cleanup-complete-fixes-pending
Basis: `ce79c2f`

## Bereinigte Wahrheit

- `182` war eine rohe Constructor-Site-Zahl und ist kein Control-,
  Fortschritts- oder Qualitaetswert.
- Factory-Expansion ergibt 222 statische Deklarationsstellen. Auch diese Zahl
  ist keine Runtime-Widgetzahl, weil Schleifen datenabhaengig Widgets erzeugen.
- 182 automatische Testtreffer sind nur Kandidaten: Review fand 105 reine
  Modulnamen-/Importtreffer; viele restliche Treffer pruefen nur Tooltip,
  Existenz, Text oder direkten Handler statt Control-Signalweg.
- Strenger Static-only-Review: 36 echte Element-Belegluecken, zwei
  Current-Pfad-Caveats und zwei voll belegte Controls.
- Kein breiter oder neuer UI-Test wurde ausgefuehrt.

## Produktfindings

### B-901 — Update-Controls default unerreichbar

`ENABLE_VERSION_CHECK=False`; Download/Close-Banner bleibt im Defaultpfad
unsichtbar. Default-Repo im Version-Service ist veraltet/falsch. Da Controls
nicht sichtbar sind, zaehlen sie nicht als belegte sichtbare STAB-5-Aktionen.

### B-902 — About-Dokumentation im installierten Build stiller No-Op

About-Handler oeffnet nur `<bundle-root>/README.md`, falls vorhanden.
PyInstaller-/Installer-Payload packt README nicht. Dev-Checkout funktioniert,
installierte App reagiert sichtbar ohne Wirkung.

## Planbereinigung

- Genau ein Plan ist aktiv: `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16`.
- Aeltere Registry-Plaene sind `superseded`; offene Tasks sind als in den
  Master uebertragen markiert.
- Viele historische Dateien liegen physisch weiter unter `plans/`. Ihre Lage
  macht sie nicht aktiv; Registry plus `ACTIVE_PLAN.md` sind Autoritaet.
- Exhaustive Audit bleibt bewusst pausiert/`blocked`, nicht superseded.
- Keine Datei wurde geloescht oder verschoben: physische Massenarchivierung
  wuerde Links brechen und braucht einen separaten, expliziten Move-Plan.

## Naechste einzige Task

`STAB-5 / B-902 About-Dokumentation im installierten Build funktionsfaehig machen`.
