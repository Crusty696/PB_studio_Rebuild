# PB Studio Exhaustive Line + Feature-State Audit Execution Plan

> **Status:** `draft` — Planung dokumentiert; keine Audit-Ausfuehrung, kein Fix,
> kein ACTIVE_PLAN-Wechsel autorisiert.
>
> **REQUIRED SUB-SKILL:** `pb-exhaustive-audit-ledger`
>
> **Team-Skills bei Ausfuehrung:** `pb-agent-team-architect`,
> `project-audit-team`, `dispatching-parallel-agents`,
> `pb-live-verify-orchestrator`, `pb-functional-tester`,
> `pb-vault-compliance-scribe`, `pb-workflow-regression-chief`.

**Plan-ID:** `PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15`
**Datum:** 2026-08-15
**Planart:** Read-only Vollaudit; Findings und Evidenz schreiben, Produktcode nicht
aendern. Fixes brauchen spaeter eigenen autorisierten Fixplan.
**Kanonischer Workspace:**
`C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`
**Hardware-Grenze:** ausschliesslich NVIDIA GTX 1060 / `cuda:0`; sonst CPU.
**Aktueller Governance-Blocker:** `ACTIVE_PLAN.md` nennt W4 Videoanalyse als
naechste Task; Registry-Zeile nennt noch B-819/W3. Audit darf erst nach expliziter
Userwahl und Governance-Abgleich aktiv werden.

---

## 1. Ziel und nicht verhandelbare Zusagen

Ziel: gesamten definierten PB-Studio-Projektumfang ohne Sampling bilanzieren,
jede Textzeile zweimal unabhaengig semantisch pruefen, jede Nicht-Zeilen-Einheit
direkt pruefen, jeden Symbol-/Wiring-/Config-/Persistenzpfad dispositionieren und
jede Nutzerfunktion samt realen Betriebszustaenden nachweisen.

Dieser Plan verspricht nicht vorab, dass Code korrekt ist. Er verspricht ein
pruefbares Verfahren, das jede nicht gepruefte Einheit sichtbar laesst.

Pflichtresultate:

1. Hashgebundener Snapshot aller Einheiten aus festem `audited_commit`.
2. Lueckenloses Zwei-Pass-Zeilenledger.
3. Nicht-Zeilen-Ledger fuer Binaer-, Leer-, generierte und Metadaten-Einheiten.
4. Symbol-, Import-, Call-, Qt-Signal-, Config-, DB-, Worker- und Packaging-Graph.
5. Featurekatalog aus Nutzeraktionen und automatischen Triggern.
6. Symbol-State-Ledger fuer jede Funktion/Methode plus 17-Achsen-Zustandsmatrix
   je Feature und je alternativer Implementierung.
7. Content-addressed Livebelege gegen exakt `audited_commit` fuer Erfolg,
   Ergebnis, Fehler, Cancel, Retry,
   Cleanup und Neustart, soweit Feature diese Zustaende besitzt.
8. Adversarial validierte Findings: Defekte, tote Pfade, Attrappen,
   Doppelimplementierungen, Inkonsistenzen, unkonfigurierte Leser/Schreiber,
   fehlende Migrationen, falsche Statusaussagen und Evidenzluecken.
9. Vollbericht mit exakter `not_checked`-Liste; leer nur bei belegtem Nullbestand.

Verboten waehrend Audit:

- Produktcodefixes, Refactorings, Dependency-Wechsel, Status `fixed`.
- Befund nur aus Grep, Linter, Testname oder Alt-Handoff ableiten.
- Sampling auf Gesamtbestand hochrechnen.
- Ein gruener Pfad als Beweis fuer alternative Pfade verwenden.
- Agenten gleichzeitig im selben Worktree schreiben lassen.
- unbekannte/ungetrackte Dateien still ignorieren.
- fehlende Harnesses waehrend laufender Auditwellen nachbauen.
- freie Runtime-Referenzen, Reviewer-Namen oder Current-HEAD-Aussagen als
  Beweiskette akzeptieren.

---

## 2. Gepruefte Ausgangslage, noch keine Audit-Ergebnisse

Reconnaissance am Planungs-HEAD `0a8ad8b`:

| Messung | Wert | Bedeutung |
|---|---:|---|
| Tracked Dateien | 1.851 | Planungs-Snapshot; bei Audit neu erzeugen |
| UTF-8-Textdateien | 1.842 | breiter Inventarlauf |
| Textzeilen | 344.962 | keine Aussage ueber Korrektheit |
| Binaerdateien | 9 | eigene Direktpruefung erforderlich |
| Python-Dateien | 1.236 | AST-parsebar: 1.236/1.236 |
| Funktionen/Methoden | 10.949 | Symboluniversum, nicht Featurezahl |
| Klassen | 1.291 | Symboluniversum |
| Imports | 10.302 | statische Kantenkandidaten |
| Call-Nodes | 78.319 | statische Kantenkandidaten |
| Tests | 815 Dateien / 114.924 Zeilen | ebenfalls komplett zu auditieren |
| Runtime-Produkt | 353 Dateien / 118.991 Zeilen | kein exklusiver Auditumfang |
| Docs/Governance/Evidenz | 496 / 80.107 Zeilen | ebenfalls direkt pruefen |
| Ops/Build/Assets | 131 / 20.328 Zeilen | ebenfalls direkt pruefen |
| Config | 24 / 5.524 Zeilen | Reader/Writer-Vertrag pruefen |
| Vendor | 27 / 4.650 Zeilen | nicht automatisch ausschliessen |
| Nullbyte/Leerdateien | 19 Kandidaten | Bedeutung einzeln dispositionieren |

Dynamik-Risikokandidaten: 588 `getattr`, 1.297 `setattr`, 35 `exec`, 15
`__import__`, 22 `import_module`, 13 `eval`. Diese Zahlen sind Suchresultate,
keine Findings.

Groesste Produktdateien: `ui/timeline.py` 4.457 Zeilen, `main.py` 2.372,
`services/video_analysis_service.py` 2.125, `services/pacing_service.py` 1.994,
`services/export_service.py` 1.980, `services/brain/legacy_sqlite.py` 1.952.

Bekannter Startzustand: ungetrackte D-089-Testartefakte existieren. Eigentum und
Aufnahme/Ausschluss muessen vor Audit-Snapshot durch Userentscheidung geklaert
werden; sie duerfen nicht geloescht, committed oder still ausgeschlossen werden.

---

## 3. Architekturvarianten und Entscheidung

### Variante A — ein linearer Reviewer

Vorteil: einheitliche Interpretation. Nachteil: keine unabhaengige Gegenpruefung,
Kontextverlust bei >344.000 Zeilen, keine breite Parallelitaet. Verworfen.

### Variante B — reine Verzeichnis-Silos

Vorteil: schnell parallelisierbar. Nachteil: UI kann gruen wirken, waehrend
Service/Worker/DB-Pfad tot ist; Doppelpfade bleiben verdeckt. Verworfen.

### Variante C — Evidence-Ledger + disjunkte Dateiowner + Cross-Layer-Tracks

Ein Director besitzt Scope/Queue/Vault. Evidence Custodian besitzt Bundle und
Masterledger. Spezialisten besitzen disjunkte Dateien.
Jede Textzeile erhaelt zwei unabhaengige Passes. Separater Verifier besitzt
End-to-End-Featuretracks. Adversarial Reviewer sieht Findings erst nach eigener
Pruefung. Gewaehlt, weil nur diese Variante direkte Zeilenabdeckung und
funktionsbezogene Laufzeitzustaende gleichzeitig beweisen kann.

---

## 4. Teamstruktur und Parallelitaetsgrenze

Teamname: **PB Studio Exhaustive Audit Team**.

Technische Grenze: vier gleichzeitige Slots inklusive Hauptagent. Daher maximal
drei Worker parallel pro Welle. Mehr Rollen werden in sequenziellen Wellen
besetzt; keine Behauptung unbegrenzter Parallelitaet. Gesamtzahl eingesetzter
Agenten/Subagenten ist nicht auf diese vier Slots begrenzt: Director skaliert
Roster über beliebig viele rotierende Wellen, sobald zusätzlicher disjunkter
Scope oder unabhängiger Gegenbeweis Nutzen bringt.

| Rolle | Exklusiver Besitz | Aufgaben |
|---|---|---|
| Audit Director | Registry, Scope, Queue | Orchestrierung; darf weder Shards manuell mergen noch allein Completion signieren |
| Evidence Custodian | externes Bundle, Batchimport | immutable Shards, Hashmanifest, atomarer Import, Recovery |
| Lead G Governance | docs/config/build/governance | Plaene, Handoffs, Packaging, Dependencies, Configquellen |
| Lead R Runtime | `services/**` | Domainlogik, GPU, FFmpeg, Ollama, Pipelines, Ressourcen |
| Lead D State | `database/**`, `workers/**`, Storage | ORM, Migration, Transaktion, Lifecycle, Restart, Cleanup |
| Lead U Surface | `main.py`, `ui/**`, resources/translations | UI-Aktion, Shortcut, Signal, Controller, Erreichbarkeit |
| Lead V Evidence | `tests/**`, scripts/tools/reports | Tests, Harness, Artefakte, unabhaengige Runtimebeweise |
| Adversarial Reviewer | keine Erstpass-Datei | Finding-Challenge, falsche Positive/Negative, Gegenbeweis |

Arbeitsregel:

- Jeder Agent: eigener Worktree unter `.worktrees/audit-<wave>-<role>` und Branch
  `codex/audit-<wave>-<role>`.
- Claim vor Zugriff; Heartbeat unter 15 Minuten; Handoff sauber.
- Agenten schreiben nur eigene immutable Ledger-Shards, nie Produktdateien.
- Evidence Custodian importiert nur vollstaendige validierte Batches atomar.
  Director besitzt keinen manuellen Mergepfad. Kein `git add -A`.
- Pass-B-Reviewer darf nicht Pass A derselben Datei sein.
- Cross-Layer-Track hat einen Verifier als alleinigen Workflowowner, ohne
  Dateiownership der statischen Reviewer zu ueberschreiben.
- Leads dürfen abgegrenzte Subagenten einsetzen. Parent bleibt für Scope,
  Evidenzqualität und sauberen Handoff verantwortlich; Parent/Child teilen nie
  denselben Worktree und bearbeiten nie dieselbe Ledger-Einheit gleichzeitig.
- Zusätzliche Besetzung ist Pflicht, wenn Warteschlange sonst Spezialgebiete
  vermischt, Pass-A/Pass-B-Unabhängigkeit verletzt oder Runtime-Gegenbeweis
  ohne zweiten Spezialisten bliebe.
- Director-SPOF-Gate: Queue, Signoffs und Hashmanifest werden maschinenlesbar
  rekonstruiert; Lead V und Adversarial Reviewer signieren Completion getrennt.
  Director-Ausfall darf keinen Shardverlust und keine unrekonstruierbare
  Entscheidung verursachen.

---

## 5. Evidenzmodell und Abschlussarithmetik

Kanonische Arbeitsartefakte pro Auditlauf ausserhalb Produkt-Worktree, z. B.
`C:\Users\David_Lochmann\Documents\PB_studio_Audit_Evidence\<run-id>\`.
In-Repo-Ausgabe ist verboten: sie macht Clean-Gate selbst rot. Nach finaler
Validierung wird unveraenderliches Bundle gehasht; nur Report + Bundlehash
werden in separatem Abschlusscommit ins Repo uebernommen:

```text
snapshot.json
audit_contract.json
delta_ledger.jsonl
reviewer_roster.jsonl
files.jsonl
line_ranges_pass_a.jsonl
line_ranges_pass_b.jsonl
non_line_units.jsonl
symbols.jsonl
symbol_states.jsonl
edges.jsonl
config_contracts.jsonl
db_contracts.jsonl
worker_lifecycles.jsonl
duplicates.jsonl
exclusions.jsonl
features.jsonl
requirements_universe.jsonl
trigger_universe.jsonl
feature_states.jsonl
runtime_runs.jsonl
command_runs.jsonl
findings.jsonl
finding_challenges.jsonl
not_checked.jsonl
completion.json
atomic_import.json
report.md
```

Jeder Record bindet mindestens `run_id`, `audited_commit`, Snapshot-ID, Dateipfad,
Datei-SHA, Reviewer-ID, Zeitstempel und Beleg. Zeilenranges: 100–200 Zeilen,
exakt 1..EOF, keine Luecken/Ueberlappungen. Dateien mit weniger Zeilen bilden
eine Range. Binaer- und Leerdateien erhalten je Pass eine Nicht-Zeilen-Einheit.

Zwei unterschiedliche Aussagen:

- `100 % inventarisch bilanziert`: jede Einheit direkt geprueft oder mit
  expliziter, usergenehmigter Exklusion dispositioniert.
- `100 % direkt geprueft`: keine Exklusion; A+B pruefen jede Textzeile und jede
  Nicht-Zeilen-Einheit direkt.

Rechenregeln in `completion.json`:

```text
inventory_rate = dispositionierte_dateien / snapshot_dateien
pass_a_line_rate = eindeutige_A_zeilen / direkte_textzeilen
pass_b_line_rate = eindeutige_B_zeilen / direkte_textzeilen
non_line_rate = signierte_A_B_einheiten / erwartete_A_B_einheiten
symbol_rate = dispositionierte_symbole / extrahierte_symbole
edge_rate = dispositionierte_kanten / extrahierte_kanten
requirements_exact_set = exakt_einmal_dispositionierte_requirements / requirements_universum
trigger_exact_set = exakt_einmal_dispositionierte_trigger / trigger_universum
feature_state_rate = ausgefuellte_17_achsen / erwartete_17_achsen
runtime_verified_rate = validierte_runtime_pflichtachsen / erwartete_runtime_pflichtachsen
unknown_rate = unknown_pflichtachsen / erwartete_pflichtachsen
delta_clean = 1 wenn kein produktrelevantes_delta_und_ttl_gueltig sonst 0
```

Unqualifizierter Abschluss nur wenn alle Nenner und Zaehler gespeichert,
Hashes identisch, Inventar-/A-/B-/Symbol-/Requirements-/Trigger-Raten exakt 1.0,
`runtime_verified_rate=1.0`, `unknown_rate=0`, `delta_clean=1`, TTL gueltig,
genehmigte Exklusionen mathematisch getrennt und alle Phase--1-Validatoren Exit
0 sind. Sonst: qualifizierter Teilbericht mit exakten Raten und Restledger;
Wort `vollstaendig` ohne Qualifikation verboten.

Automatische Tools erzeugen Kandidaten und Abdeckungsbelege. Sie vergeben nie
semantischen Signoff und nie `YES` fuer Laufzeitverhalten.

---

## 6. Feature-Zustandsvertrag

Feature-ID wird pro Nutzeraktion oder automatischem Trigger gebildet, nicht pro
Datei. Alternative Implementierungen erhalten getrennte Pfad-ID, z. B.
Timeline-Vorschau vs Auto-Edit, Audio klassisch vs V2, Legacy-Pacing vs
Studio-Brain-Fallback.

Pflichtfelder je Feature:

`feature_id`, `path_id`, `user_surface`, `trigger`, `handler`, `service`,
`worker`, `state_store`, `config_keys`, `expected_result`, `evidence_age`,
`verdict`, `blockers`, `not_checked`.

Pflichtachsen:

| Achse | Beweisfrage |
|---|---|
| `declared` | Feature/Trigger existiert? |
| `configured` | alle noetigen Werte, Defaults, Writer/Reader vorhanden? |
| `wired` | Signal/Callback/Registry erreicht vorgesehenen Handler? |
| `reachable` | realer Nutzer-/Systempfad erreichbar? |
| `enabled` | reale Preconditions aktivieren Funktion? |
| `executed` | Lauf gegen exakt `audited_commit` trat in Funktion ein? |
| `result` | erwartetes sichtbares/maschinenpruefbares Resultat entstand? |
| `persisted` | erwarteter DB-/Datei-/Settingszustand gespeichert? |
| `restart_safe` | Neustart/Reopen erhaelt korrekten Zustand? |
| `error` | erzwungener Fehler endet ehrlich und recoverable? |
| `cancel` | Cancel erreicht Worker/Task/DB/UI korrekt? |
| `retry` | Retry startet kanonischen Pfad mit korrektem Altzustand? |
| `cleanup` | Threads, Prozesse, Locks, Tempfiles, GPU-Speicher frei? |
| `GPU` | GTX 1060/cuda:0 oder dokumentierter CPU-Pfad korrekt? |
| `DB` | Schema, Transaktion, Isolation, Migration, Delete/Restore korrekt? |
| `UI` | Zustand, Progress, Fehler, Ergebnis sichtbar und ehrlich? |
| `live_evidence` | hashvalidiertes Runtime-Manifest/Log/Artefakt/Postcondition gegen `audited_commit` vorhanden? |

Werte: `YES`, `PARTIAL`, `NO`, `N-A`, `UNKNOWN`. Jede Zelle braucht Beleg;
`N-A` braucht Begruendung. `UNKNOWN` ist ehrliches Ergebnis, kein fehlender
Record. `executed/result/live_evidence=YES` nur content-addressed Evidence-ID
aus `runtime_runs.jsonl`, deren Command, Input, Artefakte, Exit-Code und
Postcondition real geoeffnet/gehasht wurden und exakt `audited_commit` binden.
`restart_safe=YES` nur nach realem
Restart/Reopen. Error/Cancel/Retry nur nach erzwungenem realem Pfad.

Feature-State und Symbol-State bleiben getrennte Universen. Jede extrahierte
Funktion/Methode besitzt genau einen `symbol_states.jsonl`-Record mit
Feature-/Supportzuordnung, Caller/Frameworkhook, Input/Output/Seiteneffekt-/
Fehler-/Config-/Persistenzvertrag sowie Runtime-Evidence-ID oder begruendetem
Non-Runtime-Vertrag. `UNKNOWN` bleibt erlaubt als ehrlicher Zustand, blockiert
aber unqualifizierte Completion.

---

## 7. Vollstaendige Feature-Domaenen

Katalogisierung muss mindestens folgende Domaenen gegen automatisch gefundene
Trigger reconciliieren:

1. Appstart, Systemcheck, GPU/NVENC, DB-Bootstrap, Shutdown.
2. Projekt create/open/save/recent/rename/delete/reopen/isolation.
3. Media Import, Folder, Dedupe, Search, Delete, Trash, Restore, Grid.
4. Audio klassisch, Audio V2, Einzelstufen, Batch, Stem-Separation, Mixer,
   Auto-Duck, Cancel, Retry, fehlendes Stem.
5. Videoanalyse, Pipeline, Reanalyse, defekter Clip, Proxy, Keyframes,
   Caption, Embedding.
6. Schnitt-Vorschau, Auto-Edit, Timeline CRUD, Undo/Redo, Locks, Snapshots,
   Anchors, Waveform, Thumbnails, Preview.
7. Studio Brain sechs Tabs, Graph, Entscheidungs-Explorer.
8. Brain V3 Panel, Feedback, Learning, WeightStore, EmbeddingCache.
9. Chat, Agent, Tools, Vision, Ollama, Modelmanager.
10. Convert, Effekte, Vorschau.
11. Export Preview, Final, Crossfade, Audio/Video-Codecs.
12. Storage-Provenance, Reuse, Browser, Bundle, Backup/Restore.
13. Settings, Profile, Shortcuts, QSettings, Env, Migration.
14. Packaging, Installer, Update, Frozen-Runtime, Ressourcen.

Quelle-Reihenfolge: UI-Oberflaechen → Controller/Handler → Service → Worker →
Persistenz → Config → Runtimekante → Evidenz. Zusaetzlich CLI, Scripts,
automatische Timer, Startup-/Shutdown-Hooks, DB-Callbacks und dynamische
Registries.

---

## 8. Ausfuehrungsphasen

### Phase -1 — Audit-Harness fertigstellen, vor Aktivierung

Diese Phase ist **Planungs-/Tooling-Voraussetzung**, kein Audit. Plan bleibt
`draft`; kein Snapshot, keine Range, kein Runtime-Lauf beginnt vorher.

Alle sechs Harnesses muessen implementiert, dokumentiert und durch positive
sowie gezielte negative Contracttests belegt sein:

Grundumbau innerhalb derselben Phase: bestehende Inventory-/Line-/Feature-
Scripts duerfen nicht mehr Current HEAD/Workingtree als Auditobjekt voraussetzen;
sie muessen explizites `--audited-commit <full-sha>` lesen und Gitobjekte dieses
Commits pruefen. Alter Current-HEAD-Modus darf kein revidiertes Completion-Gate
passieren.

1. Requirements-/Trigger-Enumerator + Exact-Set-Validator: unabhaengige
   Universen, Hashbindung, fehlende/zusaetzliche/doppelte Disposition rot.
2. `tools/audit_symbol_contracts.py`: jede Funktion/Methode exakt einmal;
   fehlendes Symbol, Caller, Kante oder Statevertrag rot.
3. `tools/audit_runtime_evidence.py`: immutable Scenario-Katalog; Tool fuehrt
   fest gebundene Commands selbst mit `shell=False` im detached Auditcommit-
   Kontext aus, erfasst Exit/Output/Postcondition/Trace und leitet Coverage aus
   Singleton-Featuretarget plus beobachteten Symbolen ab. Gehashte,
   selbstgeschriebene PASS-Dateien oder `covered_*`-Arrays sind kein Beleg.
4. `tools/audit_reviewer_roster.py`: Live-Enrollment gegen aktuelle
   Session-Registry und reale Worktrees vor deren Release; hashgebundene
   Session-Receipts fuer Finalgate. A/B gleiche Session oder direkte/indirekte
   Vorfahrbeziehung rot. Gemeinsamer neutraler Director ohne Signoff erlaubt.
5. Delta-/TTL-Validator: exakte Git-Diff-Pfadmenge, Produktrelevanz,
   `audited_commit`, Integrations-HEAD und Ablaufzeit; Drift/TTL rot.
6. Completion-/Atomic-Import-Harness: alle Shardhashes und referenziellen
   Mengen erst im temporaeren Ziel pruefen, danach atomarer Rename; Fehler
   laesst altes Masterledger byteidentisch. UNKNOWN-Pflichtachse rot fuer
   unqualifizierte Completion.

Pflicht-Testmatrix je Harness:

- mindestens ein positiver Minimalfall;
- fehlende ID/Zeile/Datei/Artefakt;
- manipuliertes Hash-/Commit-/Snapshotfeld;
- doppelte und fremde ID;
- veraltete TTL/produktrelevantes Delta, falls anwendbar;
- Crash/Fehler vor atomarem Swap mit Bytevergleich Altbestand;
- gleiche Session, umbenannter Reviewer, Vorfahr/Nachfahre und erfundene
  Session/Worktree fuer Unabhaengigkeitsgate; gemeinsamer neutraler Director
  als Positivfall.

Phase--1-Gate: alle sechs Werkzeuge existieren, komplette Contracttests gruen,
Negativtests beweisen rote Gates, Lead V plus Adversarial Reviewer liefern
getrennten Signoff. Erst danach darf Registrystatus auf
`approved-for-implementation` und Planaktivierung zur Userentscheidung stehen.

### Phase 0 — Governance-, Scope- und Sicherheitsgate

**Task 0.1: Aktivierungsentscheidung**

- User entscheidet explizit genau eine Variante: W4 zuerst abschliessen;
  W4 mit dokumentiertem Zwischenstand pausieren und Audit aktivieren; oder
  Audit nicht starten. Kein Agent trifft diese Prioritaetsentscheidung.
- Registry/ACTIVE_PLAN-Drift B-819/W3 vs W4 zuerst korrigieren.
- Planstatus nur nach Userentscheidung aendern.
- Gate: genau ein aktiver Plan, Vault-Mirror und Decision stimmen exakt.
- Bei W4-Pause: letzter W4-Commit, Verificationstatus, offene Schritte und
  sicherer Resume-Befehl in Repo/Vault-Handoff; kein implizites Superseden.

**Task 0.2: Scopegrenze ohne Annahmen**

User entscheidet einzeln:

- bekannte ungetrackte D-089-Artefakte;
- Git-ignored lokale Dateien, externe Modellgewichte, Ollama-Modelle;
- Vault, User-Settings, geschuetzte reale DBs;
- Vendor/generated/installer/binary/fixtures;
- externe Dependencies: Quellcodeaudit oder nur Version/Provenienz/Integration.

Kein Default-Ausschluss. Entscheidung in `exclusions.jsonl` und D-Decision.

**Task 0.3: Laufumgebung**

- `git remote -v`, HEAD, Status, Worktrees, Sessions, Submodules, LFS, ignored
  inventory, Python/Qt/CUDA/FFmpeg/Ollama-Versionen erfassen.
- Geschuetzte Pfade hashen; isoliertes Projekt/DB/QSettings-Verzeichnis.
- Keine App bei rotem Systemcheck; kein alternativer GPU-Backend.
- Gate: sauberer/erklaerter Snapshot, keine fremde Live-Session.

### Phase 1 — Deterministischer Snapshot und Universum

**Task 1.0: Auditcommit einfrieren**

- vollstaendigen Git-SHA als `audited_commit` festlegen; niemals `HEAD` als
  beweglichen Alias speichern.
- `audit_contract.json` mit Snapshot-, Universums-, Roster-, Runtime- und
  Symbolhash sowie TTL versiegeln.
- Auditreader lesen Git-Objekte dieses Commits. Report-/Harness-/Dokumentations-
  commits aendern Auditobjekt nicht.
- `delta_ledger.jsonl` bildet jede Pfadaenderung bis Integrations-HEAD exakt ab.
  Produktrelevantes Delta oder TTL-Ablauf → Reaudit/Rebase, kein Abschluss.

**Task 1.1: Inventar bauen**

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> --run-id <run-id> `
  --audited-commit <full-git-sha>
```

- Tracked, ignored, untracked, submodule/LFS/external Einheiten getrennt.
- Erster Discovery-Lauf darf Exit 2 liefern: offene Scopeeinheiten sind nicht
  signierbar. Userentscheidung/Expansionmanifest danach in
  `<scope-decisions.jsonl>`; finaler Lauf:

```powershell
python .agents/skills/pb-exhaustive-audit-ledger/scripts/build_inventory.py `
  --root . --output <evidence-dir> `
  --scope-decisions <scope-decisions.jsonl> --run-id <run-id> `
  --audited-commit <full-git-sha>
```

- Included ignored/external Wurzeln werden rekursiv vollstaendig inventarisiert
  und als normale `origin=scope`-Rows denselben A/B-Gates unterstellt.
- Encoding/EOL/Bytes/Zeilen/Blob/SHA/Mode/Kategorie erfassen.
- Gate: zweite unabhaengige Zaehlung identisch; Differenzen dispositioniert.

**Task 1.2: Reviewpakete generieren**

- Text in disjunkte 100–200-Zeilenpakete.
- Gegenwaertiger Richtwert bei 150 Zeilen: ca. 2.300 Pakete pro Pass, ca.
  4.600 Signoffs. Exakte Zahl entsteht nur aus aktivem Snapshot.
- Binaer-/Leerdatei-Einheiten erzeugen.
- Gate: Vorabvalidator beweist 1..EOF ohne Luecke/Ueberlappung; Roster und
  Lineage fuer geplante A/B-Zuteilung sind hashgebunden.

**Task 1.3: Symbol- und Kantenbasis**

- Python AST plus Qt-Regex plus Config/ORM/YAML/TOML/JSON/PowerShell/Batch-
  Parser.
- Alle Funktionen, Klassen, Imports, Calls, dynamischen Imports, reflection,
  signals/slots, registries, subprocesses, file/db/config accesses.
- Parserfehler sind Stop-Gate, nie stille Exklusion.

**Task 1.4: Immutable Shards und Importprobe**

- Externe Wave-Shards nach Signoff read-only/content-addressed versiegeln.
- Vollstaendigen Batch in temporaeres Masterledger importieren; Hash-, Roster-,
  Snapshot- und referenzielle Gates vor Swap.
- Absichtlicher Negativfall beweist: fehlgeschlagener Import veraendert altes
  Masterledger nicht.
- Keine Range-/Shard-Repo-Commits. Repo erhaelt erst final Report und
  Evidence-Bundlehash; `audited_commit` bleibt Zielobjekt.

### Phase 2 — Feature- und Vertragskatalog vor Codebewertung

**Task 2.1: Triggerinventar**

- alle `QAction`, `addAction`, Buttons, Tabs, Menus, Shortcuts, Signals,
  `clicked/triggered/currentChanged.connect`, CLI und Auto-Hooks.
- Requirements-Universum getrennt aus autorisierten Plaenen, UI-Texten,
  Schemas und expliziten Produktvertraegen erzeugen.
- Trigger-Universum unabhaengig aus UI, CLI, Scripts, Timer, Startup/Shutdown,
  DB-Callbacks und dynamischen Registries erzeugen.
- Jeder Requirements-/Trigger-ID genau eine Feature-/Support-/Dead-Candidate-
  Disposition. Exact-set-Validator: keine fehlende, zusaetzliche oder doppelte
  ID. Universumshashes sind Teil des Auditvertrags.

**Task 2.2: Cross-Layer-Vertraege**

- Trigger → Handler → Service → Worker → Persistenz → Callback → UI Resultat.
- Inputs, Outputs, Errors, Cancel, Retry, Cleanup, Config und Ownership.
- Alternative Pfade separat; Fallback nicht als Hauptpfadbeweis.

**Task 2.3: Erwartungsorakel**

- Erwartetes Resultat aus UI-Text, autorisiertem Plan, Testvertrag und Schema.
- Widersprueche als Finding, nicht eigenmaechtig entscheiden.
- Unklare Produktabsicht → eine gezielte Userfrage, Feature bleibt UNKNOWN.

### Phase 3 — Pass A: Bottom-up Zeile fuer Zeile

Je Range liest Reviewer reale Zeilen samt minimal noetigem Kontext. Pflichtcheck:

- Semantik, Preconditions, Typen, Grenzen, Null/leer/degraded.
- Erfolgs-, Fehler-, Timeout-, Cancel-, Retrypfade.
- Zustandswechsel, Idempotenz, Race, Lock, Thread-/Prozessownership.
- IO, DB, Files, Cache, Temp, Path, Cleanup, Shutdown, Restart.
- GPU/CPU, VRAM, FFmpeg, Ollama, subprocess, Packaging.
- UI-Signal/Callback/Registry/Reflection-Wiring.
- Testbezug und fehlende Negativ-/Integrationsbelege.

Reviewer signiert erst nach direkter Sichtung. Findings erhalten exakte
`path:line`, Root-Cause-Hypothese klar als Hypothese, Beweisbedarf und Scope.

Wellen, jeweils bis drei parallele Reviewer:

1. G: Governance/Docs/Config; R: Services Audio/Video; U: Main/UI Shell.
2. D: DB/Migration; R: Pacing/Brain/Export; U: Timeline/Studio Brain.
3. D: Worker/Storage; V: Tests erste Haelfte; G: Build/Installer/Scripts.
4. V: Tests zweite Haelfte; R: Restservices; U: Restwidgets/Resources.
5. Vendor/generated/binary/fixtures nach User-Scopeentscheidung.

Nach jedem Rangepaket: immutable externe Ledger-Shard, Validator, Vault-Log
durch Director. Kein Range-/Shard-Repo-Commit. Evidence Custodian importiert
nur abgeschlossene Batches atomar. Kein Sammellog am Wellenende.

### Phase 4 — Pass B: unabhaengig Top-down

- Andere Reviewer, vertauschte Ownership.
- B sieht A-Findings erst nach eigenem Signoff.
- Pruefung aus Feature-/Architekturperspektive: Warum existiert Zeile? Wer ruft
  sie? Welcher Zustand erreicht sie? Welcher Consumer nutzt Resultat?
- Danach A/B-Diff: Konflikte bleiben offen, bis dritter Referee mit Beleg
  entscheidet.
- Gate: Coverage-Validator Exit 0, verschiedene Reviewer, Hash identisch.

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

Direkter CLI ist bis Live-Enrollment-Harness bewusst rot. Phase -1 muss einen
neuen receiptgebundenen Entry-Point oder Ersatzvalidator implementieren;
rohe Session-ID-Sets sind ausdruecklich verboten.

### Phase 5 — Kanten-, Vertrag- und Duplikatabgleich

**Task 5.1: Calls und Wiring**

- Jede Definition: direkte/dynamische Caller, Frameworkhook oder nachgewiesen
  unreferenziert.
- Jede Funktion/Methode: eigener Symbol-State-Record; Feature-/Supportrolle,
  Input/Output/Seiteneffekt/Fehler/Config/Persistenz sowie Runtime-Evidence-ID
  oder begruendeter Non-Runtime-Vertrag.
- Jede Qt-Verbindung: Senderlebenszeit, Slot, Signatur, Thread, Consumer.
- `pass`, TODO, NotImplemented, leere Handler, immergleiche Returnwerte einzeln.

**Task 5.2: Config-Contracts**

- Jeder Key: Default, Writer, Reader, UI, Env, Migration, Packaging,
  unbekannt/legacy.
- Orphan Writer, Orphan Reader, Defaultdrift, falscher Typ, UI-ohne-Consumer.

**Task 5.3: DB/Persistenz**

- 25 ORM-Modelle plus gesamte Alembic-Kette, Constraints, Indizes, downgrade,
  cascade, timestamps, project isolation.
- Jeder Statuswechsel: writer/reader/UI/restart/error/cancel/retry.

**Task 5.4: Doppel-/Alternativpfade**

- Hash-/AST-/Tokenaehnlichkeit erzeugt Kandidaten.
- Semantische Reviewer entscheiden duplicate, fork, fallback, legacy,
  intentional parallel oder false positive.
- Ein Pfad darf anderen nie verdecken.

**Task 5.5: Handoff- und Evidenzdrift**

- Jede Claude-/Codex-/Vault-Behauptung gegen `audited_commit` und reale
  content-addressed Artefakte.
- Historische Evidenz bleibt historisch; nicht auf `audited_commit` uebertragen.

### Phase 6 — Funktions- und Feature-Livekampagnen

Reihenfolge verhindert Cross-Contamination:

1. Boot/Systemcheck/Shutdown.
2. Projekt/Storage/Media.
3. Audio klassisch/V2/Cancel/Retry/Restart.
4. Video/defekter Clip/Reanalyse/Cancel.
5. Timeline/Schnitt/Undo/Locks/Waveform/Thumbnails.
6. Brain/Feedback/Learning/Graph.
7. Chat/Ollama/Tools/Vision/Modelwahl.
8. Convert/Export.
9. Packaging/Frozen/Installer/Update.

Jeder einzelne Run:

- Exakter `audited_commit`/Snapshot, Eingabemanifest und erwartete Postcondition.
- UI-Klick-/Shortcut-Beleg, Logzeitraum, Task-/Worker-ID.
- DB/Datei/Settings/GPU/Prozess Pre/Post.
- sichtbares Ergebnis oder exakter Fehler; Command, Input, Exit-Code, Logs,
  Artefakte und Postconditions content-addressed im Runtime-Manifest.
- Cleanup/Post-Process-Count; Projektwechsel/Restart wo relevant.
- geschuetzte Hostpfade unveraendert.

Zustaende werden getrennt ausgefuehrt: Happy, leer/degraded, Fehler, Cancel,
Retry, Restart. Erster reproduzierbarer Fehler stoppt nur aktuellen Workflow;
Finding wird dokumentiert, kein Fix. Andere unabhaengige Audittracks duerfen
weiterlaufen, solange kein gemeinsamer Sicherheits-/Snapshotdefekt besteht.

GPU-Laeufe serialisiert. Nur `cuda:0`, `-hwaccel cuda`, `h264_nvenc` oder
`hevc_nvenc`; Bibliothek ohne CUDA → CPU. VRAM/Prozessbelege pro Lauf.

### Phase 7 — Adversarial Finding-Validation

Jedes Finding bekommt:

1. Finderbeleg.
2. unabhaengige Reproduktion oder `audited_commit`-Quellbeweis.
3. Gegenhypothese und Suche nach dynamischem Consumer/Fallback.
4. Auswirkung, Reichweite, Severity, Reproduzierbarkeit.
5. Status `confirmed`, `rejected`, `needs-user-decision` oder
   `not-reproduced`; nie `fixed`.

Pflichtgegenproben:

- entferne/mutiere Testorakel nur isoliert, um Testwirksamkeit zu zeigen;
- pruefe, ob Source-Inspection-Test echten Pfad nur vortaeuscht;
- pruefe Altartefakt gegen Commit/Snapshot;
- pruefe dynamische Imports/Qt registries vor Dead-Code-Aussage;
- pruefe alternative Pfade einzeln.

### Phase 8 — Completion und Vollbericht

Director erzeugt:

- Executive Summary ohne Beschwichtigung.
- Scope und genehmigte Exklusionen.
- exakte Zaehler/Raten und Hashbindung.
- Architektur-/Feature-/State-Matrix.
- Findings nach Severity und Domain.
- tote/leere/unkonfigurierte/doppelte Pfade.
- Testqualitaet und falsche Sicherheit.
- Runtime-, GPU-, DB-, UI-, Packagingzustand.
- widerspruechliche Altbehauptungen.
- `not_checked`-Liste und Blocker.
- separaten, noch nicht autorisierten Fixplan-Backlog.

Abschlussreview durch Lead V plus Adversarial Reviewer, getrennte Signoffs.
Report darf `vollstaendig` ohne Qualifikation nur sagen, wenn Completion-Gates
mathematisch gruen, `unknown_rate=0`, `runtime_verified_rate=1`, TTL gueltig und
`delta_clean=1` sind. Sonst genaue Teilraten und Restledger. Director allein
darf Abschluss nicht freigeben.

---

## 9. Bekannte Kandidaten, die neu bewiesen werden muessen

Diese Punkte sind Recon-Hinweise, keine abschliessenden Findings:

- Gewichtsprofil wird gesnapshottet/loggt; Auto-Edit-Scorer scheint `default`
  fest zu verwenden.
- Pins scheinen keinen nachgewiesenen Schnitt-Consumer zu haben; Boost/Exclude
  sind getrennt.
- Raster-Config besitzt Leser, aber keine gefundene UI.
- `global_min_duration` scheint Parser/Schema ohne Anwendungsleser.
- mehrere `StylePreset`-Gewicht-/Clipdauerfelder scheinen ohne Consumer.
- `Timeline generieren` und Auto-Edit sind getrennte Pfade.
- Video-Pool-Detailkartenhandler enthaelt explizites `pass`.
- `verdictChanged`, `statsRefreshed`, `GraphView.set_active_scene` haben noch
  keinen bewiesenen Consumer.
- Batched Crossfade und Ollama-Crash-Abhilfe sind live unverifiziert.
- Legacy/Studio-Brain, Audio classic/V2 und mehrere Brain-Systeme koexistieren.

Korrektur zur historischen Uebergabe: Current HEAD enthaelt Scheduler-Caller
fuer EmbeddingCache sowie Feedback-/WeightStore-Schreibpfade und term→axis
Credit-Mapping. Alte Aussage „tot/uniform“ darf nicht uebernommen werden.

---

## 10. Toolingplan und ehrlicher Implementierungsstand

Bereits vorhanden, aber nur fuer alten Teilvertrag lokal validiert:

- `.agents/skills/pb-exhaustive-audit-ledger/SKILL.md`
- `scripts/build_inventory.py`
- `scripts/verify_line_coverage.py`
- `scripts/verify_feature_matrix.py`
- `scripts/self_test.py`

Diese vorhandenen Scripts beweisen **nicht** Requirements-/Trigger-Exact-Set,
Symbol-State-Vollstaendigkeit, reale Runtime-Artefakte, Reviewer-Lineage,
Delta/TTL oder atomaren Completion-Import. Auditstart damit verboten.

In Phase -1 vor Aktivierung zu implementieren und per Positiv-/Negativtests zu
beweisen; Dateinamen sind Planvorgabe, keine Behauptung vorhandener Dateien:

1. `tools/audit_feature_inventory.py`: Requirements-/Trigger-Universen,
   AST + Qt/CLI/Auto-Hooks und Exact-Set-Gate.
2. `tools/audit_symbol_contracts.py`: Symbol-/Import-/Call-/Dynamic-Kanten plus
   Symbol-State-/Config-Vertraege je Funktion/Methode.
3. `tools/audit_runtime_evidence.py`: content-addressed Runtime-Manifeste und
   Artefakt-/Postcondition-Validierung gegen `audited_commit`.
4. `tools/audit_reviewer_roster.py`: Roster, Session, Parent-Lineage,
   Worktree/Claims und A/B-Unabhaengigkeit.
5. `tools/audit_delta_ttl.py`: exakte Delta-Pfadmenge, Produktrelevanz,
   Auditbasis und TTL.
6. `tools/audit_completion.py`: immutable Shardhashes, alle Nenner,
   referenzielle Integritaet, UNKNOWN-Gate und atomarer Batchimport.

Duplicate-, DB-, Worker- und Packaging-Kandidaten werden von obigen
Universums-/Symbolharnesses als spezialisierte Parsermodule geliefert oder
explizit als zusaetzliche Phase--1-Abhaengigkeit dokumentiert. Kein fehlendes
Modul darf erst waehrend Pass A/B erfunden werden.

Ruff, Pyright/Mypy, Bandit, Vulture, Radon, pip-audit und Duplikatscanner sind
nur ergaenzende Kandidatengeneratoren. Versionen werden vor Installation
festgeschrieben. Kein Tool ersetzt direkte Zeilenpruefung.

---

## 11. Definition of Done

Audit ist nur abgeschlossen, wenn:

- [ ] User hat Plan aktiviert; genau ein Plan aktiv.
- [ ] Phase -1: sechs Harnesses implementiert; Positiv-/Negativtests gruen und
      zwei unabhaengige Signoffs vorhanden.
- [ ] `audited_commit` als voller SHA eingefroren; Audit liest dessen Gitobjekte.
- [ ] TTL gueltig; Delta-Ledger exakt; kein produktrelevantes offenes Delta.
- [ ] Scope jeder tracked/untracked/ignored/external Einheit entschieden.
- [ ] Snapshot clean/erklaert und unveraendert.
- [ ] Inventarzaehler durch unabhaengige Methode identisch.
- [ ] Pass A jede direkte Textzeile genau einmal abdeckt.
- [ ] Pass B jede direkte Textzeile genau einmal abdeckt.
- [ ] A/B je Datei verschiedene Reviewer.
- [ ] Jede Binaer-/Leerdatei A+B direkt dispositioniert.
- [ ] Jede Exklusion einzeln vom User genehmigt.
- [ ] Jedes Symbol und jede Kante dispositioniert.
- [ ] Jede Funktion/Methode besitzt Symbol-State-Record mit Runtimebeleg oder
      begruendetem Non-Runtime-Vertrag.
- [ ] Requirements-/Trigger-Universen unabhaengig gehasht; Exact-set je ID.
- [ ] Alternative Pfade getrennte Pfad-IDs besitzen.
- [ ] Jede Feature-ID alle 17 Achsen mit Beleg/Begruendung besitzt.
- [ ] Runtime-Evidence-IDs oeffnen/hashpruefen Command, Input, Exit-Code,
      Artefakte, Postconditions und binden `audited_commit`.
- [ ] Livekampagnen Erfolg/Fehler/Cancel/Retry/Restart gegen `audited_commit`
      abdecken; keine Pflichtachse bleibt UNKNOWN fuer unqualifizierte Completion.
- [ ] GPU-/DB-/UI-/Prozess-/Datei-Postconditions gespeichert.
- [ ] Jedes Finding unabhaengig challenged.
- [ ] Keine Produktdatei im Auditplan geaendert.
- [ ] `not_checked` explizit und vollstaendig.
- [ ] Completion-Validator Exit 0.
- [ ] Reviewer-Roster beweist A/B-Unabhaengigkeit ueber Session und Lineage.
- [ ] Immutable Shards atomar importiert; Negativtest bewahrt Altledger bytegleich.
- [ ] Repo-Report, Vault-Synthese, `log.md`, `index.md` synchron.
- [ ] Handoff sauber, commits gepusht, mindestens eine belegte Lektion.
- [ ] User entscheidet spaeter separat ueber Findings/Fixplan und `fixed`.

---

## 12. Naechste erlaubte Aktion

Solange Status `draft`: nur Planreview und Phase--1-Tooling nach eigener
Autorisierung. Keine Audit-Ausfuehrung. Vor Aktivierung muessen sechs Harnesses
plus Contracttests belegt sein. Danach entscheidet User explizit, ob W4 zuerst
endet, dokumentiert pausiert oder Audit nicht startet; ferner Scopeantwort fuer
untracked/ignored/external Einheiten. Keine dieser Entscheidungen trifft Agent.
