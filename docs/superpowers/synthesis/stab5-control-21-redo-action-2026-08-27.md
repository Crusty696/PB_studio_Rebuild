# STAB-5 Control #21 — Redo-Aktion

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `PBWindow`-Build → `_create_workspaces()` → Window-QAction `Redo` mit
`QKeySequence.StandardKey.Redo` → `timeline_view.undo_stack.redo`.

## Ergebnis

- Candidate-Refs waren semantisch fremd und kein Elementbeleg.
- Echte PBWindow-Konstruktion erzeugt genau eine sichtbare/aktive Redo-QAction
  mit Window-Parent und Standard-Redo-Shortcut.
- Vorab undone MarkerCommand im echten Timeline-QUndoStack geht durch
  QAction-Trigger von Zustand 0 auf 1; Stack wird danach undo-faehig.
- Nur ChatDock-Host/Ollama-Rand und Close-Prompt isoliert.
- Gezielter Test `1 passed in 11.05s`.
- Kein Produktcodeedit.

## Offen

Physischer Ctrl+Y/Ctrl+Shift+Z-Benutzerinput in sichtbarer gestarteter App fehlt.
Daher nicht `fixed`.
