---
name: pb-exhaustive-audit-ledger
description: Build and validate a hash-bound, line-complete, two-pass PB Studio audit ledger plus per-feature runtime-state matrix. Use for whole-project audits that must prove every tracked file/line was directly reviewed or explicitly excluded, and every app function/feature was traced from entrypoint through UI, controller, service, worker, DB/config, result, failure, restart, and live evidence. Never use this skill to authorize fixes or claim runtime behavior from static evidence.
---

# PB Exhaustive Audit Ledger

## Modus

- Nur Deutsch zum User; Caveman ultra fuer Updates.
- `audit-plan`/`audit-execution` strikt von Fixes trennen.
- AGENTS.md, Plan Registry, Active Plan, Decision und Vault zuerst pruefen.
- Nie `fixed`, `verified`, `works` aus Source, Test oder Ledger ableiten.
- Ein Snapshot-HEAD. Drift invalidiert betroffene Signoffs.

## Ablauf

1. Gitstatus, Remote, Worktrees, Sessions pruefen.
2. Governance-Widerspruch → STOP; nur Draft/Recon erlaubt.
3. Evidence-Verzeichnis ausserhalb Produkt-Worktree anlegen. In-Repo-Ausgabe
   macht Clean-Gate selbst rot und ist verboten. Snapshot erzeugen:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> --run-id <run-id>
```

4. Erster Lauf ist Discovery. Dirty State oder offene Scopewurzel erzeugt
   Scope-Artefakte und Exit 2; kein signierbarer Snapshot. `snapshot.json`,
   `files.jsonl` und `workspace_units.jsonl` kontrollieren. Untracked Dateien
   und ignored Wurzeln einzeln entscheiden. Jede aufgenommene ignored/externe
   Wurzel vollstaendig expandieren und als gehashtes Manifest angeben. Danach
   finalen Snapshot mit User-Decision-Ledger versiegeln:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> `
  --scope-decisions <scope-decisions.jsonl> --run-id <run-id>
```

   Keine implizite Exklusion.
5. Textdateien in disjunkte 100-200-Zeilen-Ranges teilen. Pass A und B durch
   verschiedene Reviewer. Reviewer B sieht A-Findings erst nach eigenem Signoff.
6. Ranges nach `references/ledger-schema.md` schreiben.
7. Beide Passes pruefen:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/verify_line_coverage.py `
  --root . --snapshot <evidence-dir>/snapshot.json `
  --inventory <evidence-dir>/files.jsonl `
  --pass-a <evidence-dir>/line_ranges_pass_a.jsonl `
  --pass-b <evidence-dir>/line_ranges_pass_b.jsonl `
  --non-line-units <evidence-dir>/non_line_units.jsonl `
  --exclusions <evidence-dir>/exclusions.jsonl `
  --workspace-units <evidence-dir>/workspace_units.jsonl
```

8. Feature-IDs aus UI-Aktionen, Shortcuts, automatischen Triggern, CLI-/Script-
   Entrypoints und Backend-Aktionen bilden. Nicht eine Feature-ID pro Datei erfinden.
9. Pro Feature UI → Controller → Service → Worker/Task → DB/Datei/Config →
   Callback/UI-Ergebnis → Cleanup verfolgen. Alternative Pfade separat halten.
10. Matrix pruefen:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/verify_feature_matrix.py `
  --root . --snapshot <evidence-dir>/snapshot.json `
  --inventory <evidence-dir>/files.jsonl `
  --workspace-units <evidence-dir>/workspace_units.jsonl `
  --matrix <evidence-dir>/feature_states.jsonl
```

11. Findings getrennt challengen. Automatische Kandidaten sind kein Befund.
12. Abschluss nur bei Validator Exit 0, clean/identischem Snapshot, genehmigten
    Exklusionen, signierten Binaer-/Leerdatei-Einheiten und sichtbaren
    UNKNOWN-/Not-checked-Zellen. Validatoren sind notwendige, nie allein
    hinreichende Evidenz fuer semantische Korrektheit.

## Pflichtpruefungen pro Zeilenrange

- Semantik, Eingaben, Outputs, Seiteneffekte.
- Erfolg, leer/degraded, Fehler, Cancel, Retry.
- Cleanup, Shutdown, Projektwechsel, Restart.
- UI-/Signal-/Callback-/Registry-/Reflection-Wiring.
- DB Writer/Reader/Migration/Delete/Restore.
- Config Default/Writer/Reader/UI/Env/Packaging.
- GPU nur GTX 1060 `cuda:0`; FFmpeg nur CUDA/NVENC oder CPU.
- Tests gegen Produktionspfad; Source-Inspection-Test kennzeichnen.

## Feature-State-Regel

Achsen: `declared`, `configured`, `wired`, `reachable`, `enabled`, `executed`,
`result`, `persisted`, `restart_safe`, `error`, `cancel`, `retry`, `cleanup`,
`GPU`, `DB`, `UI`, `live_evidence`.

Werte: `YES`, `PARTIAL`, `NO`, `N-A`, `UNKNOWN`.

- Jede Zelle braucht objektbasierte, Commit- und Zeit-gebundene Evidenz;
  `N-A` braucht `kind=n-a` plus Begruendung.
- `executed`, `result`, `live_evidence` = `YES` nur Current-HEAD-Lauf.
- `restart_safe` = `YES` nur Persistenz + Appneustart/Reopen.
- Error/Cancel/Retry = `YES` nur erzwungener realer Pfad.
- Unit/Integration nie als GUI-Livebeweis verkaufen.

## 100-Prozent-Sprache

- `100 % inventarisch bilanziert`: direkte Reviews + genehmigte Exklusionen.
- `100 % direkt geprueft`: Pass A/B jede Textzeile direkt; jede Binaer-/
  Metadateneinheit ebenfalls direkt geprueft.
- Kein Prozent aus Sampling hochrechnen. Nicht gepruefte Einheit bleibt sichtbar.

## Stop-Gates

Stoppen bei Governance-/HEAD-/Blob-Drift, unbekanntem Dirty State, falscher DB,
nicht zugestelltem GUI-Klick, Crash, fremdem GPU-Backend, fehlender Fixture,
widerspruechlicher Evidenz, notwendigem Codefix oder Produktentscheid.

## Ressourcen

- `references/ledger-schema.md`: JSONL-Schemas und Completion-Regeln.
- `scripts/build_inventory.py`: HEAD-reiner Git-Snapshot plus untracked Dateien/
  ignored Scopewurzeln; Dirty-State fail-closed.
- `scripts/verify_line_coverage.py`: Zwei-Pass-Zeilen- und Nicht-Zeilen-Validator.
- `scripts/verify_feature_matrix.py`: Feature-Achsen-/Evidenzvalidator.
