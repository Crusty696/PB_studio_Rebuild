# STAB-5 Control #15 — KI-Chat-Anzeige

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebaute sichtbare Tools-Menueaktion `KI Chat anzeigen` → versteckter
KI-Chat-Proxy → PBWindow-Tabrouting → produktiv gemounteter `CHAT`-Tab im
sichtbaren ContextPanel/Dock.

## Ergebnis

- Candidate-Refs prueften Tooltip bzw. fremdes Statuspanel, nicht diese Aktion.
- Echter WorkspaceSetupController erzeugt Tools-Menue, QAction und Proxy.
- QAction sichtbar/aktiv; Proxy bleibt unsichtbar.
- PBWindow-Closure/Connect sowie produktive `PanelSetupController`-Montage des
  `CHAT`-Tabs mutationssensitiv quellguardiert.
- Aktion oeffnet ContextPanel/Dock und wechselt von Tasks auf Chat.
- Gezielter Test `1 passed in 11.10s`.
- Kein Produktcode geaendert.

## Offen

Echter PBWindow-Vollstart mit produktivem ChatDock/LLM fehlt. Daher nicht
`fixed`.
