# STAB-5 Control #10 — Kontextpanel

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter `Kontext`-Button → echter QTest-Mausclick → produktiver
Cross-file-Connect → `PBWindow._set_context_panel_visible(bool)` → echter
ContextPanel und QDockWidget → Checked-, Sichtbarkeits- und Breitenzustand.

## Evidence-Abgleich

- Tooltip-Candidate prueft nur Quelltextattribut.
- AnalysisStatusPanel-Candidate betrifft fremde Oberflaeche.
- Frontend-Contract prueft nur ContextPanel direkt, keinen Button/Dock/Wiring.

## Ergebnis

- Testhost ist gezeigtes QMainWindow mit echtem ContextPanel und QDockWidget.
- Produktcontroller baut echten checkbaren Button mit Text `Kontext`.
- Click 1: checked, Panel/Dock sichtbar, Mindestbreite aktiv.
- Click 2: unchecked, Panel/Dock verborgen, Maximalbreite 0.
- Exakte Guards schuetzen reale Button→Handler- und Dock→Sync-Connects, bevor
  isolierter Harness dieselben Verbindungen herstellt.
- Gezielter Test: `1 passed in 4.62s`; Nachreview PASS.
- Kein Produktcode geändert.

## Offen

Kein PBWindow-Vollstart/gespeicherter RestoreState-Livepfad. Daher nicht
`fixed`.
