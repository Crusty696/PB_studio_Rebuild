# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-AREA-AUDIT-2026-05-24
next_allowed_task: Area 2: Database, Migrations, Storage, Soft-Delete
updated: 2026-05-24

## Meaning

Der User hat am 2026-05-24 bestaetigt, dass eine neue eigene Bereichspruefung fuer die ganze PB-Studio-App angelegt und als aktiver Fokus ausgefuehrt werden soll.

Aktiver Plan:

```text
PB-STUDIO-AREA-AUDIT-2026-05-24
```

Der vorher aktive Plan `COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22` ist pausiert, nicht geloescht.

## Agent Behavior

- Nur `PB-STUDIO-AREA-AUDIT-2026-05-24` ausfuehren.
- Dieser Plan ist Audit-only: keine App-Code-Aenderungen, keine Refactors, keine Fixes.
- Ergebnis je Bereich: statische Pruefung, Testzuordnung, sichere Smokes/Tests, Vault-Synthesis, konkrete Bug-Dateien nur bei belegten Findings.
- Gewaehlte Prueftiefe: Bereichs-Gates.
- Gewaehltes Ergebnis: Befunde + priorisierter Fixplan.
- Audio-V2-Portierung bleibt ausserhalb dieses Plans, ausser reine Befunde werden dokumentiert.
- Bestehende Dirty-Worktree-Aenderungen bleiben erhalten und werden nicht revertet.
- `verified` / `fixed` nur nach realem App-Workflow plus Log-/UI-Beleg.

## Current Status

- Area 1 ist audit-complete-live-open.
- Belegter neuer Bug: `B-348` blockiert globales `pytest --collect-only`.
- Naechster erlaubter Task: Area 2.
