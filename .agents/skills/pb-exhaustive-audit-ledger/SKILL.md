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
- Ein unveraenderliches `audited_commit`. Workingtree-/Branch-HEAD ist keine
  Auditidentitaet. Delta nach Freeze wird separat bilanziert und darf alte
  Signoffs nie still aktualisieren.

## Ablauf

1. Gitstatus, Remote, Worktrees, Sessions pruefen.
2. Governance-Widerspruch → STOP; nur Draft/Recon erlaubt.
3. **Vor Aktivierung** Phase -1 des autorisierten Plans abschliessen: alle
   benoetigten Generatoren, Validatoren, Schemas sowie positive und negative
   Contracttests muessen real existieren und gruen sein. Der aktuelle Skill
   liefert diese Vollkette noch nicht; vorhandene drei Scripts sind nur
   Teilbausteine und koennen keinen Abschluss nach revidiertem Vertrag
   bescheinigen.
4. Evidence-Verzeichnis ausserhalb Produkt-Worktree anlegen. In-Repo-Ausgabe
   macht Clean-Gate selbst rot und ist verboten. Nach Phase--1-Umbau Snapshot
   mit explizitem Zielcommit erzeugen:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> --run-id <run-id> `
  --audited-commit <full-git-sha>
```

   Achtung: aktuelles Script unterstuetzt `--audited-commit` noch nicht. Dieser
   Aufruf ist Zielvertrag, nicht aktuell ausfuehrbarer Befehl.

5. Erster Lauf ist Discovery. Dirty State oder offene Scopewurzel erzeugt
   Scope-Artefakte und Exit 2; kein signierbarer Snapshot. `snapshot.json`,
   `files.jsonl` und `workspace_units.jsonl` kontrollieren. Untracked Dateien
   und ignored Wurzeln einzeln entscheiden. Jede aufgenommene ignored/externe
   Wurzel vollstaendig expandieren und als gehashtes Manifest angeben. Danach
   finalen Snapshot mit User-Decision-Ledger versiegeln:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> `
  --scope-decisions <scope-decisions.jsonl> --run-id <run-id> `
  --audited-commit <full-git-sha>
```

   Keine implizite Exklusion.
6. `audited_commit` aus Git-Objekten einfrieren. Snapshot, Inventar und jede
   Evidenz binden genau diesen Commit. Spaetere Branch-Aenderungen kommen in
   `delta_ledger.jsonl`; abgelaufene TTL oder produktrelevantes Delta blockiert
   Abschluss bis Rebase/Neuaudit. Reportcommit bleibt ausserhalb Auditobjekt.
7. Requirements-/Trigger-Universum unabhaengig erzeugen, hashen und gegen
   Featurekatalog per exakter Mengengleichheit pruefen. Fehlender, zusaetzlicher
   oder doppelt dispositionierter Trigger blockiert.
8. Textdateien in disjunkte 100-200-Zeilen-Ranges teilen. Pass A und B durch
   Reviewer aus hashgebundenem Roster. Verschiedene Namen reichen nicht:
   Session, Parent-Lineage, Worktree und Claims muessen Unabhaengigkeit belegen.
   Reviewer B sieht A-Findings erst nach eigenem Signoff.
9. Ranges nach `references/ledger-schema.md` schreiben. Shards bleiben
   immutable im externen Evidence-Verzeichnis. Keine Range-Repo-Commits.
   Masterledger nur per validiertem, atomarem Batchimport austauschen.
10. Beide Passes pruefen. Folgender existierender Validator deckt nur bisherigen
    Teilvertrag; er ist bis Phase -1 kein Abschlussgate fuer revidierten Audit:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/verify_line_coverage.py `
  --root . `
  --snapshot <evidence-dir>/snapshot.json `
  --inventory <evidence-dir>/files.jsonl `
  --pass-a <evidence-dir>/line_ranges_pass_a.jsonl `
  --pass-b <evidence-dir>/line_ranges_pass_b.jsonl `
  --non-line-units <evidence-dir>/non_line_units.jsonl `
  --exclusions <evidence-dir>/exclusions.jsonl `
  --workspace-units <evidence-dir>/workspace_units.jsonl `
  --reviewer-roster <evidence-dir>/reviewer_roster.jsonl
```

   Dieser aktuelle CLI-Aufruf ist absichtlich fail-closed: ohne in-process
   Live-Enrollment-Attestierung aus dem noch fehlenden
   `tools/audit_reviewer_roster.py` kann er keinen Completion-PASS liefern.

11. Feature-IDs aus UI-Aktionen, Shortcuts, automatischen Triggern, CLI-/Script-
   Entrypoints und Backend-Aktionen bilden. Nicht eine Feature-ID pro Datei erfinden.
12. Jede Funktion/Methode in `symbol_states.jsonl` dispositionieren:
    Feature-/Supportzuordnung, Caller/Frameworkhook, Konfig-/Statevertrag sowie
    Runtimebeleg oder begruendeter Non-Runtime-Vertrag. Featurematrix ersetzt
    Symbol-State-Ledger nicht.
13. Pro Feature UI → Controller → Service → Worker/Task → DB/Datei/Config →
   Callback/UI-Ergebnis → Cleanup verfolgen. Alternative Pfade separat halten.
14. Runtimebelege ausschliesslich ueber content-addressed Records in
    `runtime_runs.jsonl`: Command/Input/Artefakte/Postconditions werden geoeffnet,
    gehasht und an `audited_commit`, Snapshot und Run gebunden. Matrixzellen
    referenzieren `evidence_id`; freie Ref-Strings sind kein Beleg.
15. Matrix pruefen. Folgender existierender Validator deckt nur bisherigen
    Teilvertrag; Abschluss erst nach Phase--1-Erweiterung und deren Contracttests:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/verify_feature_matrix.py `
  --root . `
  --snapshot <evidence-dir>/snapshot.json `
  --inventory <evidence-dir>/files.jsonl `
  --workspace-units <evidence-dir>/workspace_units.jsonl `
  --matrix <evidence-dir>/feature_states.jsonl `
  --requirements-triggers <evidence-dir>/requirements_triggers.jsonl `
  --runtime-runs <evidence-dir>/runtime_runs.jsonl `
  --evidence-root <evidence-dir>
```

   Auch dieser CLI ist bis zum fehlenden, selbst ausfuehrenden
   `tools/audit_runtime_evidence.py` bewusst fail-closed. Gehashte,
   selbstgeschriebene PASS-Dateien sind keine Runner-Attestierung.

16. Findings getrennt challengen. Automatische Kandidaten sind kein Befund.
17. Abschluss nur bei allen Phase--1-Validatoren Exit 0, identischem
    `audited_commit`, genehmigten Exklusionen, exakten Universumsmengen,
    signierten Nicht-Zeilen-/Symbol-Einheiten und validierten Runtimebelegen.
    `UNKNOWN` auf einer Pflichtachse blockiert unqualifizierte Aussage
    `Audit vollstaendig`; erlaubt sind nur getrennte Raten plus Restledger.
    Validatoren sind notwendige, nie allein hinreichende Evidenz.

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
- `executed`, `result`, `live_evidence` = `YES` nur Lauf gegen exakt
  `audited_commit` mit validierter `evidence_id`.
- `restart_safe` = `YES` nur Persistenz + Appneustart/Reopen.
- Error/Cancel/Retry = `YES` nur erzwungener realer Pfad.
- Unit/Integration nie als GUI-Livebeweis verkaufen.

## 100-Prozent-Sprache

- `100 % inventarisch bilanziert`: direkte Reviews + genehmigte Exklusionen.
- `100 % direkt geprueft`: Pass A/B jede Textzeile direkt; jede Binaer-/
  Metadateneinheit ebenfalls direkt geprueft.
- Kein Prozent aus Sampling hochrechnen. Nicht gepruefte Einheit bleibt sichtbar.

## Stop-Gates

Stoppen bei Governance-/Auditcommit-/Blob-Drift, unbekanntem Dirty State, falscher DB,
nicht zugestelltem GUI-Klick, Crash, fremdem GPU-Backend, fehlender Fixture,
widerspruechlicher Evidenz, notwendigem Codefix oder Produktentscheid.

## Ressourcen

- `references/ledger-schema.md`: JSONL-Schemas und Completion-Regeln.
- `scripts/build_inventory.py`: HEAD-reiner Git-Snapshot plus untracked Dateien/
  ignored Scopewurzeln; Dirty-State fail-closed.
- `scripts/verify_line_coverage.py`: Zwei-Pass-Zeilen-/Nicht-Zeilen-Validator
  gegen festes `audited_commit` plus hashgebundenes Reviewer-Roster/Lineage.
- `scripts/verify_feature_matrix.py`: Requirements-/Trigger-Exact-Set,
  Feature-Achsen und content-addressed Runtime-Evidenz.
- `scripts/verify_symbol_states.py`: Symboluniversum-Exact-Set und Runtime-/
  Non-Runtime-Vertrag je Funktion/Methode.
- `scripts/verify_audit_readiness.py`: fail-closed Phase--1-Gate fuer exakte
  Harness-/Testmenge aus festem Tooling-Commit. Extern gepinnter separater
  Authoritycommit bindet feste Gate-Matrix, Validator-/Dependency-Blobs und
  Testquellen; Reviewer-Verifikation laeuft aus isolierter Blobmaterialisierung.
- `scripts/self_test.py`, `scripts/self_test_identity_snapshot.py`,
  `scripts/self_test_feature_evidence.py`: integrierte und gezielte Positiv-/
  Negativvertraege. Gruene Selftests ersetzen keinen realen Auditlauf.

## Noch fehlende Phase--1-Werkzeuge

Bereits als Skill-Teilvertraege vorhanden und getestet: Requirements-/Trigger-
Exact-Set, Symbol-State, content-addressed Runtime-Evidence, Reviewer-Roster-/
Lineage und `audited_commit`-gebundene Coverage. Nicht als vollstaendige
Phase--1-Harnesses behandeln: kanonische Universumsgeneratoren, Delta-/TTL-
Validator und atomarer Completion-Importer fehlen; sechs im Plan vorgegebene
`tools/audit_*.py` samt `tests/audit/test_*.py` existieren nicht vollstaendig.
`verify_audit_readiness.py` muss deshalb fail-closed rot bleiben. Auditstart
damit verboten.

Vorhandene Teilvalidatoren beweisen nur ihre Eingabevertraege. Sie beweisen
nicht, dass Generatoren jedes Requirement, jeden Trigger, jede dynamische Kante
oder jedes Delta gefunden haben. Completion bleibt bis Phase--1-Harnesses und
zwei unabhaengige Signoffs unzulaessig.

Readiness-PASS benoetigt zwei verschiedene Inputs fuer denselben Authority-SHA:
beweglichen `authority_commit` sowie separat verwahrten
`expected_authority_commit`. Das Programm kann eine gemeinsame Kompromittierung
beider Caller-Werte nicht erkennen. Ohne echten externen Pin und real
provisionierte Reviewer-Schluessel ist nur struktureller Selftest moeglich;
operationaler Readiness-Status bleibt NO-GO.
