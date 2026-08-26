# STAB-5 Control #7 — Add-Anchor-Szenenauswahl

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Sichtbarer `+ Anker`-Button → `_add_anchor_dialog()` → `scene_combo` →
`currentData()/currentText()` → QTree-Anchor-Item → Anchor-Collector.

## Evidence-Abgleich

- Frühere Candidate-Refs prüften Medien-Checkboxen bzw. Auto-Edit/Progress,
  nicht den Anchor-Dialog.
- Aktiver Callsite ist belegt: WorkspaceSetup verbindet sichtbaren Schnitt-
  Button mit dem EditWorkspaceController-Dialog.

## Ergebnis

- Echter Dialog mit Combo/Spinbox, isolierter DB-Abfrage und Modal-Rückgabe.
- Gewählte Szenen-ID `scene-42` erreicht TreeItem-UserRole und Collector.
- Sichtbares Szenenlabel und Consoleeintrag stimmen.
- Erster Lauf scheiterte nur an ungültigem SimpleNamespace-Dialogparent.
- Mit echtem QMainWindow-Parent: `1 passed in 1.30s`.
- Drei geführte Read-only-Prüfer bestätigen gültigen Auswahlpfad.
- Kein Produktcode geändert.

## Direkter Finding

B-905: Placeholder ohne Szene kann bestätigt werden und erzeugt leeren Anchor.
Separater enger Fix folgt vor Control #8.

## Offen

- Kein echter PBWindow-/Projekt-DB-/Sync-Livepfad; daher nicht `fixed`.
