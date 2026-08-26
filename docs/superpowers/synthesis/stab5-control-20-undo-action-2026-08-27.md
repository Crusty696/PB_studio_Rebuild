# STAB-5 Control #20 — Undo-Aktion

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `PBWindow`-Build → `_create_workspaces()` → Window-QAction `Undo` mit
`QKeySequence.StandardKey.Undo` → `timeline_view.undo_stack.undo`.

## Ergebnis

- Candidate-Refs waren semantisch fremd und kein Elementbeleg.
- Echte PBWindow-Konstruktion erzeugt genau eine sichtbare/aktive Undo-QAction
  mit Window-Parent und Standard-Undo-Shortcut.
- MarkerCommand im echten Timeline-QUndoStack geht durch QAction-Trigger von
  Zustand 1 auf 0 zurueck; Stack wird danach redo-faehig.
- Nur ChatDock-Host/Ollama-Rand und Close-Prompt isoliert.
- Gezielter Test `1 passed in 11.08s`.
- Kein Produktcodeedit.

## Offen

Physischer Ctrl+Z-Benutzerinput in sichtbarer gestarteter App fehlt. Daher nicht
`fixed`.
