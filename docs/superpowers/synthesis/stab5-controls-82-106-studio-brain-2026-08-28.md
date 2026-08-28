# STAB-5 Controls #82-#106 — Studio-Brain-Tabs (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#82** AuditTab `_RunSelector._combo`: Index-Wechsel emittiert `runChanged`, setzt `_current_run_id` und lädt Cut-Tabelle für den ausgewählten Run neu.
- **#83** AuditTab `Nur abgelehnte` CheckBox: Klick setzt `rejected_only=True` im Filter und lädt Tabelle neu; erneuter Klick setzt Zustand zurück.
- **#84** AuditTab `Nur Fallback` CheckBox: Klick filtert auf `fallback_only=True`.
- **#85** AuditTab `Story Map öffnen…` Button: Klick führt `open_story_map_async` mit gewähltem Run und Tab-Parent aus.
- **#86** MemoryTab `_type_combo`: füllt Daten aus DB; Index-Wechsel setzt Filter-Property (Apply-Design, Tabelle lädt bei #87).
- **#87** MemoryTab `Anwenden` Button: Klick ruft `_on_filter_apply` auf, bringt Typ-Filter zur Wirkung und lädt Tabelle neu.
- **#88** MemoryTab `Gelerntes zurücksetzen…` Button: Klick erreicht Handler und zeigt Dialog (`QMessageBox.question`); Abbrechen-Pfad verhindert Löschung.
- **#89** SteerTab `_TrackSelector._combo`: Wechsel emittiert `trackChanged`, aktualisiert Snapshot `audio_track_id` und aktiviert Run-Button.
- **#90-#93** SteerTab entfernte Inventar-Controls: `_ProfilePicker`, `Profil bearbeiten`, `+ Pin`, `Pin entfernen` wurden in Commit `4bea226` bereinigt (User-Scope "Nur Totes + Inaktives"); Abwesenheit im Test explizit belegt.
- **#94** SteerTab Boost `− Entfernen` Button: Klick entfernt markierten Boost aus der Queue.
- **#95** SteerTab Exclude `− Entfernen` Button: Klick entfernt markierten Exclude aus der Queue.
- **#96** SteerTab `Mit diesen Einstellungen starten` Button: Klick emittiert `runRequested` mit aktuellem Snapshot und zeigt Status-Toast.
- **#97/#98** StructureTab entfernte ContextMenu-Actions: tote Doppel-Implementierung auf `_ClipCard` wurde in Commit `4bea226` entfernt; Abwesenheit explizit belegt (produktiv wirken #105/#106).
- **#99** StructureTab Ansichts-Combo (`Grid`/`Graph`): Wechsel schaltet Stack-Index um (Stack-Index 1 lädt echten Graph).
- **#100** StructureTab Rolle-Combo (`hero`/`filler`): Wechsel löst Debounce aus und filtert Cards nach 400ms.
- **#101** StructureTab Stimmung-Combo: Wechsel filtert Cards nach Stimmung.
- **#102** StructureTab Stil-Combo: Wechsel filtert Cards nach Bucket-ID.
- **#103** StructureTab Inspector `⤴ Boost im nächsten Lauf` Button: Karten-Selektion aktiviert Button; Klick fügt Boost für Scene zur Queue hinzu.
- **#104** StructureTab Inspector `⊗ Ausschließen im nächsten Lauf` Button: Klick fügt Exclude für Scene zur Queue hinzu.
- **#105** StructureTab Override-Menu `Boost im nächsten Lauf` Action: `trigger()` fügt Boost mit Source `structure` hinzu.
- **#106** StructureTab Override-Menu `Exclude im nächsten Lauf` Action: `trigger()` fügt Exclude mit Source `graph` hinzu.

## Verifikation

`tests/ui/test_stab5_studio_brain_tab_controls.py` (neu, 20 Tests). Offscreen-Qt + tmp-SQLite (Alembic head). Kein Produktcodeedit.

## Grenzen

Echte Inferenz-Läufe, Async-Brain-Operationen und Qt-Render-Views bleiben Live-Endgate.
