# Ledger-Schema

## files.jsonl

```json
{"run_id":"RUN-001","snapshot_id":"sha256","origin":"git","commit_sha":"git-sha","path":"services/x.py","git_mode":"100644","git_object_type":"blob","git_blob":"blob-sha","sha256":"file-sha","bytes":123,"media":"text","encoding":"utf-8","eol":"lf","line_count":10,"category":"runtime_product","generated_candidate":false,"lfs_pointer":false,"disposition":"direct-review","exclusion_id":null}
```

`media`: `text | binary | gitlink`. `disposition`: `direct-review | excluded-approved`.
Keine Exklusion ohne `exclusion_id` und separates, vom User genehmigtes Ledger.

`snapshot_id` wird aus allen Records ohne deren `snapshot_id` neu berechnet.
`commit_sha` ist immer `audited_commit`. Inventory stammt aus dessen
Git-Tree/Blobs, nie implizit aus Current HEAD oder gemischten Workingtree-Bytes.

## audit_contract.json

```json
{"schema_version":1,"plan_id":"PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15","run_id":"RUN-001","audited_commit":"full-40-char-sha","tooling_commit":"full-40-char-sha","snapshot_id":"sha256","frozen_at":"ISO-8601","expires_at":"ISO-8601","artifacts":{"requirements-universe":{"artifact_id":"sha256:...","ref":"requirements_universe.jsonl","sha256":"sha256","bytes":1,"record_count":1},"trigger-universe":{"artifact_id":"sha256:...","ref":"trigger_universe.jsonl","sha256":"sha256","bytes":1,"record_count":1},"feature-catalog":{"artifact_id":"sha256:...","ref":"features.jsonl","sha256":"sha256","bytes":1,"record_count":1},"symbol-catalog":{"artifact_id":"sha256:...","ref":"symbols.jsonl","sha256":"sha256","bytes":1,"record_count":1},"edge-catalog":{"artifact_id":"sha256:...","ref":"edges.jsonl","sha256":"sha256","bytes":1,"record_count":1},"runtime-scenario-catalog":{"artifact_id":"sha256:...","ref":"scenario_catalog.jsonl","sha256":"sha256","bytes":1,"record_count":1},"runtime-feature-universe":{"artifact_id":"sha256:...","ref":"runtime_feature_universe.jsonl","sha256":"sha256","bytes":1,"record_count":1},"runtime-symbol-universe":{"artifact_id":"sha256:...","ref":"runtime_symbol_universe.jsonl","sha256":"sha256","bytes":1,"record_count":1},"runtime-executor-manifest":{"artifact_id":"sha256:...","ref":"executor_manifest.json","sha256":"sha256","bytes":1,"record_count":1},"runtime-dependency-manifest":{"artifact_id":"sha256:...","ref":"dependency_manifest.json","sha256":"sha256","bytes":1,"record_count":1},"reviewer-trust-policy":{"artifact_id":"sha256:...","ref":"reviewer/trust_policy.json","sha256":"sha256","bytes":1,"record_count":1},"reviewer-contract":{"artifact_id":"sha256:...","ref":"reviewer/contract.json","sha256":"sha256","bytes":1,"record_count":1},"reviewer-readiness-binding":{"artifact_id":"sha256:...","ref":"reviewer/readiness_binding.json","sha256":"sha256","bytes":1,"record_count":1},"reviewer-spawn-journal":{"artifact_id":"sha256:...","ref":"reviewer/spawn_journal.json","sha256":"sha256","bytes":1,"record_count":1}},"contract_sha256":"canonical-body-sha256"}
```

Top-Level-Feldmenge und obige 14 Artifact-Keys sind exakt. Jeder Descriptor
hat exakt `artifact_id`, `ref`, `sha256`, `bytes`, `record_count`.
`contract_sha256` ist SHA-256 der kanonischen JSON-Bytes ohne dieses
Self-Hashfeld. Ein roher Datei-SHA ist getrennt als
`audit_contract_file_sha256` zu benennen und nie als Body-SHA zu akzeptieren.

Gemeinsame `record_count`-Regel: `.jsonl` = Zahl geparster, nichtleerer
JSON-Objektzeilen; `.json`-Array = Laenge; `.json`-Objekt mit `records`-Array =
Laenge dieses Arrays; anderes gueltiges JSON = 1; andere regulaere Datei = 1.
Parserfehler, Verzeichnis, Symlink, unsicherer Ref, Bytes-/Hash-/Count-Drift
blockieren fail-closed.

## evidence_contract.json

Top-Level entspricht Auditcontract, nutzt `completed_at` statt
`frozen_at`/`expires_at` und bindet `audit_contract_sha256` direkt. Acht
statische Record-Shards sind exakt:

```text
feature-state
feature-state-evidence
symbol-state
edge-state
symbol-state-evidence
reviewer-roster
runtime-evidence
delta-ledger
```

Dynamische Attachments stehen im selben flachen `artifacts`-Objekt:

```text
feature-proof:<evidence_id>
symbol-proof:<evidence_id>
runtime-proof:<evidence_id>
reviewer-enrollment-receipt:<session_id>
reviewer-enrollment-signature:<session_id>
reviewer-signoff:<role>:<session_id>
reviewer-signoff-signature:<role>:<session_id>
```

Exact-Closure ist Pflicht: Proofkeys entsprechen exakt ihren Evidence-Records;
Enrollment-Receipt/-Signature-Paare exakt dem Roster; Signoff-/Signature-Paare
exakt `reviewer-contract.required_signoffs`. Fehlendes, extra, orphan oder
mehrfach konsumiertes Artefakt blockiert. Signoffs binden Readiness-Basis,
nicht `evidence_contract_sha256`; Evidencecontract wird erst nach Signoffs
versiegelt und erzeugt deshalb keinen Hashzyklus.

Report-/Dokumentationscommits aendern `audited_commit` nicht. Jedes Delta
zwischen `audited_commit` und Integrations-HEAD steht in `delta_ledger.jsonl`.
Produktrelevantes Delta oder abgelaufene TTL blockiert unqualifizierte
Completion, bis neues Freeze/Rebase plus betroffene Revalidierung erfolgt.

### Runtime authority policy (Userentscheidung 2026-08-16)

Runtime-Commands duerfen den Auditcontract nicht durch ein frei mitgeliefertes
CLI-Feld autorisieren. Ein separater, extern gepinnter `authority_commit`
enthaelt am festen relativen Policy-Pfad exakt folgenden kanonischen Gitblob:

```json
{"schema_version":1,"audit_contract_sha256":"canonical-body-sha256","plan_id":"PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15","run_id":"RUN-001","snapshot_id":"sha256","audited_commit":"full-40-char-sha","tooling_commit":"full-40-char-sha","allow_same_audited_tooling_commit":false}
```

`audit_contract_sha256` ist immer SHA-256 des kanonischen Contractbodys ohne
dessen Self-Hashfeld. Ein Hash der rohen Datei heisst ausdrücklich
`audit_contract_file_sha256` und ist kein Ersatz fuer den Body-SHA.

Erzeugungs- und Vertrauenskette:

1. `audited_commit` einfrieren;
2. `tooling_commit` mit Runner/Harnesses einfrieren;
3. Auditcontract mit beiden IDs versiegeln;
4. Policy mit Contract-Body-SHA und allen obigen IDs erzeugen;
5. Policy in separatem `authority_commit` committen und dessen vollen SHA
   ausserhalb von Contract/CLI als erwarteten Pin uebergeben.

Der Policyblob enthaelt absichtlich nicht seinen eigenen `authority_commit`.
Runner loest den extern erwarteten Commit kanonisch auf, liest nur
`authority_commit:<fixed-policy-path>` und bindet Receipt an
`authority_commit`, Policy-Gitblob-OID, Policybytes-SHA und Policy-Pfad.
Policy im `tooling_commit`, `$SELF`-Sentinel oder vom Contract/CLI selbst
gesetzte Autoritaetswerte sind unzulaessig und muessen fail-closed rot werden.

## delta_ledger.jsonl

```json
{"run_id":"RUN-001","base_commit":"audited-sha","head_commit":"integration-sha","path":"services/x.py","change":"modified","product_relevant":true,"disposition":"reaudit-required","reviewer_id":"REV-3","signed_at":"ISO-8601"}
```

Erlaubte Dispositionen: `report-only`, `reaudit-required`,
`explicit-user-exclusion`. Vollstaendige Pfadmengengleichheit gegen Git-Diff
ist Pflicht.

## workspace_units.jsonl

Untracked Dateien mit Hash/Groesse sowie ignored Verzeichniswurzeln mit
`decision: unresolved`. User-Decision ist `excluded-approved` oder
`included-expanded`. Exklusion braucht Approval-Felder. Inclusion braucht
`scope_id`, absoluten `scope_root`, `expanded_manifest` und dessen SHA256.
Jede Expansionmanifestzeile besitzt eindeutigen logischen `path`, absoluten
`source_path`, `relative_path`, SHA256, Bytes, Media/Encoding/EOL/Linecount,
Kategorie, Generated-/LFS-Status und `disposition`. Builder uebernimmt diese
Rows als `origin=scope` ins normale `files.jsonl`; damit gelten dieselben
Zeilen-/Nicht-Zeilen-Gates. Scope-Dateimodus ist zwingend
`git_mode=external`, `git_object_type=file`, `git_blob=null`; reale Bytes
bestimmen Media/Zeilen. Manifest- und Inventory-source_path/Felder muessen
identisch sein. `relative_path` muss exakt reale Rootrelation sein; source_path
ist eindeutig. Symlink/Junction in included Scope blockiert fail-closed und
braucht getrennte User-Scopeentscheidung fuer reales Ziel. Validator enumeriert
Scopewurzel rekursiv und verlangt exakte Pfadmengengleichheit. Wurzelrecord
allein reicht nie.
Externe Einheiten kommen per User-Decision-Ledger in denselben Vertrag. Dirty
State oder unresolved Scope ist nicht signierbar. Workspace-Ledger-Hash und
Anzahl sind Teil von `snapshot.json` und `snapshot_id`.

## exclusions.jsonl

```json
{"run_id":"RUN-001","audited_commit":"audited-sha","snapshot_id":"sha256","exclusion_id":"EX-001","path":"vendor/x.py","reason":"...","approved_by":"user","approved_at":"ISO-8601","decision_ref":"D-..."}
```

## reviewer_roster.jsonl

```json
{"run_id":"RUN-001","audited_commit":"audited-sha","snapshot_id":"sha256","reviewer_id":"REV-1","session_id":"session-uuid","parent_session_id":"director-session","ancestor_session_ids":["director-session"],"worktree":"absolute-path-at-enrollment","branch":"codex/audit-a","commit_sha":"audited-sha","claims":["@audit/RUN-001/shards/REV-1/**"],"review_scope":["services/**"],"session_receipt_ref":"session_receipts/session-uuid.json","session_receipt_sha256":"sha256","roster_signed_at":"ISO-8601"}
```

Pass A/B derselben Einheit brauchen unterschiedliche `reviewer_id` und
`session_id`; keiner darf Vorfahr/Nachfahre des anderen sein oder dessen
Worktree/Ausgabe-Shard teilen. `review_scope` darf fuer gleiche Quelle
ueberlappen; `claims` bezeichnet ausschliesslich disjunkte Output-Shards.
Gemeinsamer neutraler Director ist zulassig, hat aber keinen Range-Signoff.
Receipt entsteht nur durch Live-Enrollment gegen Registry und realen Worktree;
freies JSON reicht nicht. Rosterhash ist Teil des Auditvertrags.

## line_ranges_pass_a.jsonl / pass_b

```json
{"run_id":"RUN-001","audited_commit":"audited-sha","snapshot_id":"sha256","pass":"A","reviewer_id":"agent-id","path":"services/x.py","file_sha256":"file-sha","start_line":1,"end_line":10,"range_sha256":"optional","checks":{"semantics":"done","errors":"done","state":"done","threading":"done","io_db_gpu":"done","wiring":"done"},"finding_ids":[],"verdict":"reviewed","signed_at":"ISO-8601"}
```

Ranges pro Datei: Start 1, Ende EOF, keine Luecke/Ueberlappung. Pass A/B Reviewer
gemaess Roster unabhaengig. Datei-SHA muss Inventory des `audited_commit`
entsprechen. Jeder Shard hat Content-SHA256, wird nach Signoff immutable und
kommt nur ueber atomaren Batchimport in das Masterledger; keine Range-Commits.

## non_line_units.jsonl

Pflicht fuer jede direkt gepruefte Binaerdatei und jede leere Textdatei, je ein
Eintrag fuer Pass A und B:

```json
{"run_id":"RUN-001","audited_commit":"audited-sha","snapshot_id":"sha256","pass":"A","reviewer_id":"agent-id","path":"resources/x.bin","unit_kind":"binary-content","file_sha256":"file-sha","checks":{"identity":"done","format":"done","provenance":"done","consumer":"done","integrity":"done"},"verdict":"reviewed","signed_at":"ISO-8601"}
```

Jede direkt gepruefte Datei braucht `metadata`. Zusaetzlich je nach Typ:
`binary-content`, `gitlink-target`, `empty-file`, `generated-provenance`.
Pass A/B muessen verschiedene Reviewer haben. Automatischer Hash-/Formatcheck
ersetzt keine direkte Inhalts-/Integrationspruefung.

## requirements_universe.jsonl / trigger_universe.jsonl / features.jsonl

```json
{"run_id":"RUN-001","universe_id":"TRIG-ui-main-001","kind":"ui-trigger","source_path":"ui/x.py","source_sha256":"file-sha","line":10,"canonical_key":"ui:x:button:start","discovered_by":"independent-enumerator","snapshot_id":"sha256","commit_sha":"audited-sha"}
```

Requirements kommen aus allen autorisierten Plan-/UI-/Schema-/CLI-/Auto-Hook-
Quellen; Trigger aus unabhaengiger statischer plus manueller Enumeration.
`features.jsonl` dispositioniert jedes `universe_id` exakt einmal als
`feature`, `support`, `dead-candidate` oder usergenehmigte Exklusion. Exact-set:
keine fehlende, zusaetzliche oder doppelte ID; beide Universumshashes sind Teil
des Auditvertrags.

## symbol_states.jsonl

```json
{"run_id":"RUN-001","symbol_id":"SYM-services.x:f","path":"services/x.py","file_sha256":"file-sha","qualified_name":"services.x.f","kind":"function","start_line":10,"end_line":20,"feature_ids":["FEAT-001"],"role":"runtime","caller_disposition":"direct-call","state_contract":{"inputs":"reviewed","outputs":"reviewed","side_effects":"reviewed","errors":"reviewed","config":"reviewed","persistence":"reviewed"},"runtime_evidence_ids":["EVID-001"],"non_runtime_reason":null,"reviewer_id":"REV-1","snapshot_id":"sha256","commit_sha":"audited-sha","signed_at":"ISO-8601"}
```

Jede extrahierte Funktion/Methode exakt einmal. Runtime-Symbol braucht
validierte Evidence-ID oder `UNKNOWN`; Non-Runtime-Symbol braucht pruefbaren
Vertrag und Begruendung. Symbol-State ist nicht aus Feature-State ableitbar.

## runtime_runs.jsonl

```json
{"run_id":"RUN-001","runtime_run_id":"LIVE-001","evidence_id":"sha256:canonical-record","audited_commit":"audited-sha","snapshot_id":"sha256","scenario_id":"SCN-FEAT-001-preview-result","scenario_sha256":"sha256","timestamp":"ISO-8601","input":{"ref":"inputs/SCN.json","sha256":"sha256"},"command":{"argv":["python","tests/runtime/scn.py"],"cwd":"."},"exit":{"code":0,"ref":"runs/LIVE-001.log","sha256":"sha256"},"postcondition":{"ref":"runs/LIVE-001-post.json","sha256":"sha256","result":"pass"},"artifacts":[],"covered_feature_paths":["FEAT-001/preview"],"covered_symbol_ids":["SYM-services.x:f"],"covered_axes":["executed","result","live_evidence"]}
```

`scenario_catalog.jsonl` bindet Scenario, Singleton-Featurepfad, erlaubte
Achsen/Symbole, Command/Input und Postcondition-Checker an audited/tooling
Commit. Runner fuehrt Command selbst aus; Runtimezeile ist Output, nicht
Behauptung. Validator oeffnet Artefakte, prueft Hash/Commit/Snapshot/Run und
akzeptiert nur in-process Runner-Attestierung. Freie oder selbstgeschriebene
PASS-Datei ist keine Evidenz.

`runtime-evidence` ist eine kompakte, vom Runner atomar publizierte Projektion
je Rich-Receipt, nicht je Symbol:

```json
{"evidence_id":"sha256:canonical-receipt","evidence_kind":"runtime","runtime_run_id":"LIVE-001","covered_feature_paths":["FEAT-001/preview"],"covered_symbol_ids":["SYM-services.x:f"],"covered_axes":["executed","result","live_evidence"],"proof_ref":"runs/LIVE-001/receipt.json","proof_sha256":"sha256","run_id":"RUN-001","audited_commit":"audited-sha","tooling_commit":"tooling-sha","snapshot_id":"sha256","timestamp":"ISO-8601","record_sha256":"sha256"}
```

`covered_feature_paths` bleibt Singleton. `covered_symbol_ids` ist eindeutig,
sortiert und darf mehrere tatsaechlich beobachtete Symbole enthalten. Der
Descriptor `runtime-proof:<evidence_id>` zeigt auf dasselbe Rich-Receipt.
Validator berechnet Receipt-ID neu und vergleicht Projektion, Receipt, Feature-,
Symbol- und Achsen-FKs exakt; keine kuenstlich duplizierte Evidence-ID.

## feature_states.jsonl

```json
{"run_id":"RUN-001","feature_id":"FEAT-001","path_id":"preview","universe_ids":["TRIG-ui-main-001"],"name":"Videoanalyse starten","user_surface":"ui","trigger":"button","handler":"ui/x.py:10","service":"services/x.py:20","worker":"N-A","state_store":"database/models.py:1","config_keys":[],"expected_result":"Analyse sichtbar","evidence_age":"audited-commit","verdict":"not-checked","blockers":[],"not_checked":["declared","configured","wired","reachable","enabled","executed","result","persisted","restart_safe","error","cancel","retry","cleanup","GPU","DB","UI","live_evidence"],"snapshot_id":"sha256","commit_sha":"audited-sha","reviewer_id":"REV-1","signed_at":"ISO-8601","states":{"declared":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"configured":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"wired":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"reachable":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"enabled":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"executed":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht ausgefuehrt","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"result":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht ausgefuehrt","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"persisted":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"restart_safe":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"error":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht erzwungen","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"cancel":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht erzwungen","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"retry":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht erzwungen","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"cleanup":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht geprueft","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"GPU":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht beobachtet","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"DB":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht beobachtet","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"UI":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"nicht beobachtet","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"live_evidence":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"pending","reason":"kein Live-Lauf","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]}},"overall_state":"not-checked"}
```

Alle 17 Achsen muessen vorhanden sein. Evidence ist Objekt, kein freier String.
Alternative Pfade teilen `feature_id`, besitzen verschiedene `path_id`.
`not_checked` entspricht exakt allen UNKNOWN-Achsen.
Runtimewerte referenzieren ausschliesslich existierende, hashvalidierte
`evidence_id` aus `runtime_runs.jsonl`.

## phase_minus_1_readiness.json

```json
{"schema_version":3,"plan_id":"PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15","run_id":"READINESS-001","tooling_commit":"full-40-char-sha","integration_head":"same-full-40-char-sha","matrix_version":1,"artifacts":[{"run_id":"READINESS-001","tooling_commit":"full-40-char-sha","path":"tools/audit_feature_inventory.py","bytes":123,"sha256":"sha256"}],"reviewer_roster_path":"absolute-external-path","reviewer_roster_sha256":"sha256","attestation_bundle_path":"absolute-external-path"}
```

Artefaktmenge entspricht exakt sechs Plan-Harnesses plus deren sechs
Contracttest-Dateien. Bytes/Hashes werden aus `tooling_commit`-Gitobjekten
berechnet. Validator ignoriert Manifest-Commands und fuehrt feste stdlib-
`unittest`-Node-IDs selbst im detached tooling_commit-Worktree aus. Readiness
berechnet/zeigt zuerst dieselbe deterministische Basis aus Matrix, Artefakten,
Commit und Rosterhash. Danach signieren Lead V und Adversarial diese Basis ueber
`audit_reviewer_roster.py finalize`; Readiness ruft den kryptographisch
gepinnten Attestation-Bundle-Validator auf. Inline-Signoffs oder frei gelieferte
Reviewer-JSONs sind unzulaessig. Fehlendes/extra Artefakt, falscher Hash, alter
Commit, fehlender Test-Node, falsche Basis/Signatur oder nicht unabhaengiger
Signoff macht Readiness rot. Repo-eigene
Tests bleiben ohne externen Trust Anchor nicht kryptographisch unverfaelschbar;
deshalb sind Validator-PASS und dualer Review beide notwendig, nie allein
hinreichend.

## Completion

Universum: jede Textzeile + Metadateneinheit pro Datei + Inhalts-/Integritaetseinheit
pro Binaerdatei + jede Funktion/Methode + Requirements-/Trigger-Exact-Set.
Getrennte Kennzahlen: `inventory_complete`, `line_pass_a_complete`,
`line_pass_b_complete`, `symbol_complete`, `feature_catalog_complete`,
`runtime_verified_rate`, `unknown_rate`, `delta_clean`.

Unqualifiziertes `Audit vollstaendig` nur bei: clean/frozen `audited_commit`,
TTL gueltig, kein produktrelevantes Delta, identische Hashes, A/B lueckenlos,
Roster-Unabhaengigkeit, vollstaendige Nicht-Zeilen-/Symbol-Einheiten,
Requirements-/Trigger-Exact-Set, genehmigte Exklusionen, alle Pflichtachsen ohne
`UNKNOWN`, validierte Runtime-Evidenz und alle Phase--1-Validatoren Exit 0.
Sonst nur qualifizierte Teilraten und vollstaendiges Restledger.

## atomic_import.json

Batchimport prueft zuerst alle Shardhashes, Roster, Snapshot, Universumsmengen
und referenzielle Integritaet in temporaerem Ziel. Nur acht statische
Record-Shards werden JSONL-geparst; Attachments werden als regulaere Dateien
ueber Descriptor, Hash, Bytes, Count und Exact-Closure geprueft. Import kopiert
alle Shards, Attachments sowie Audit-/Evidence-/Atomic-Contracts unter ihren
sicheren relativen `ref`-Pfaden und erhaelt Verzeichnisstruktur; Basename-
Flattening ist verboten. Erst danach atomarer Rename zum Masterledger. Fehler
laesst vorheriges Masterledger byteidentisch. Director editiert oder merged
keine einzelnen Rangezeilen manuell.
