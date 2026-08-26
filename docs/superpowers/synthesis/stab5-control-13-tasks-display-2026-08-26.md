# STAB-5 Control #13 — Tasks-Anzeige

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebaute sichtbare Tools-Menueaktion `Tasks anzeigen` → versteckter
interner Tasks-Proxy → PBWindow-Tabrouting → sichtbares ContextPanel/Dock →
aktiver `Tasks`-Tab.

## Ergebnis

- Candidate-Refs prueften Tooltip bzw. fremdes Statuspanel, nicht diese Aktion.
- Echter WorkspaceSetupController erzeugt Tools-Menue, QAction und versteckten
  Proxy-Button.
- Echte QAction ist sichtbar/aktiv und triggert den versteckten Proxy; Proxy
  bleibt selbst unsichtbar.
- PBWindow-Callsite und `_to_tab`-Closure sind mutationssensitiv quellguardiert.
- Aktion oeffnet ContextPanel/Dock und aktiviert case-insensitiv `Tasks`.
- Gezielter Test `1 passed in 11.74s`; Nachreview PASS.
- Kein Produktcode geaendert.

## Offen

Echter PBWindow-Vollstart mit produktivem Tasks-Tab-Inhalt fehlt. Daher nicht
`fixed`.
