# STAB-5 Control #22 — Speichern-Aktion

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `PBWindow`-Build → `_create_workspaces()` → Window-QAction `Speichern`
mit `QKeySequence.StandardKey.Save` →
`window.project_management._save_project`.

## Ergebnis

- Bestehender B-528-Test pruefte Shortcut-Wiring nur statisch; Handler-Test
  umging die QAction.
- Echte PBWindow-Konstruktion erzeugt genau eine sichtbare/aktive Window-
  QAction `Speichern` mit Window-Parent und Standard-Save-Shortcut.
- QAction-Trigger erreicht exakt das echte ProjectManagementController-Objekt.
- Nur Save-Methodenkoerper, ChatDock-Host/Ollama-Rand und Close-Prompt isoliert.
- Gezielter Test `1 passed in 9.44s`.
- Kein Produktcodeedit.

## Offen

Reale Projektpersistenz und physischer Ctrl+S-Benutzerinput in gestarteter App
fehlen. Daher nicht `fixed`.
