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
{"run_id":"RUN-001","audited_commit":"full-git-sha","snapshot_id":"sha256","frozen_at":"ISO-8601","max_age_seconds":"USER-DECISION-REQUIRED","requirements_universe_sha256":"sha256","trigger_universe_sha256":"sha256","reviewer_roster_sha256":"sha256","runtime_manifest_sha256":"sha256","symbol_states_sha256":"sha256"}
```

Im versiegelten Vertrag ist `max_age_seconds` eine positive Ganzzahl aus
expliziter Userentscheidung. Placeholder darf kein Validatorgate passieren.

Report-/Dokumentationscommits aendern `audited_commit` nicht. Jedes Delta
zwischen `audited_commit` und Integrations-HEAD steht in `delta_ledger.jsonl`.
Produktrelevantes Delta oder abgelaufene TTL blockiert unqualifizierte
Completion, bis neues Freeze/Rebase plus betroffene Revalidierung erfolgt.

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
{"run_id":"RUN-001","exclusion_id":"EX-001","path":"vendor/x.py","reason":"...","approved_by":"user","approved_at":"ISO-8601","decision_ref":"D-..."}
```

## reviewer_roster.jsonl

```json
{"run_id":"RUN-001","reviewer_id":"REV-1","session_id":"session-uuid","parent_session_id":"director-session","ancestor_session_ids":["director-session"],"worktree":"absolute-path","branch":"codex/audit-a","commit_sha":"audited-sha","claims":["services/**"],"roster_signed_at":"ISO-8601"}
```

Pass A/B derselben Einheit brauchen unterschiedliche `reviewer_id` und
`session_id`; keiner darf Vorfahr/Nachfahre des anderen sein oder dessen
Worktree/Claim teilen. Gemeinsamer Director ist zulassig, hat aber keinen
Range-Signoff. Rosterhash ist Teil des Auditvertrags. Freie Namen in
Rangezeilen reichen nicht.

## line_ranges_pass_a.jsonl / pass_b

```json
{"run_id":"RUN-001","snapshot_id":"sha256","pass":"A","reviewer_id":"agent-id","path":"services/x.py","file_sha256":"file-sha","start_line":1,"end_line":10,"range_sha256":"optional","checks":{"semantics":"done","errors":"done","state":"done","threading":"done","io_db_gpu":"done","wiring":"done"},"finding_ids":[],"verdict":"reviewed","signed_at":"ISO-8601"}
```

Ranges pro Datei: Start 1, Ende EOF, keine Luecke/Ueberlappung. Pass A/B Reviewer
gemaess Roster unabhaengig. Datei-SHA muss Inventory des `audited_commit`
entsprechen. Jeder Shard hat Content-SHA256, wird nach Signoff immutable und
kommt nur ueber atomaren Batchimport in das Masterledger; keine Range-Commits.

## non_line_units.jsonl

Pflicht fuer jede direkt gepruefte Binaerdatei und jede leere Textdatei, je ein
Eintrag fuer Pass A und B:

```json
{"run_id":"RUN-001","snapshot_id":"sha256","pass":"A","reviewer_id":"agent-id","path":"resources/x.bin","unit_kind":"binary-content","file_sha256":"file-sha","checks":{"identity":"done","format":"done","provenance":"done","consumer":"done","integrity":"done"},"verdict":"reviewed","signed_at":"ISO-8601"}
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
{"run_id":"RUN-001","evidence_id":"EVID-001","audited_commit":"audited-sha","snapshot_id":"sha256","started_at":"ISO-8601","finished_at":"ISO-8601","command":{"argv":["python","run.py"],"cwd":"absolute-isolated-path","env_manifest_sha256":"sha256"},"input_manifest":{"path":"absolute-path","sha256":"sha256"},"exit_code":0,"artifacts":[{"path":"absolute-path","sha256":"sha256","bytes":123}],"postconditions":[{"kind":"db-query","expected":"done","actual":"done","artifact_sha256":"sha256"}],"log":{"path":"absolute-path","sha256":"sha256"},"process_cleanup":{"expected":0,"actual":0},"manifest_sha256":"sha256"}
```

Validator oeffnet jedes referenzierte Manifest/Artefakt, prueft Hash, Bytezahl,
Commit, Snapshot, Run, Command, Exit-Code und Postconditions. Nicht vorhandene
Datei oder freie `ref`-Zeichenfolge ist keine Evidenz.

## feature_states.jsonl

```json
{"run_id":"RUN-001","feature_id":"FEAT-001","path_id":"preview","universe_ids":["TRIG-ui-main-001"],"name":"Videoanalyse starten","user_surface":"ui","trigger":"button","handler":"ui/x.py:10","service":"services/x.py:20","worker":"N-A","state_store":"database/models.py:1","config_keys":[],"expected_result":"Analyse sichtbar","evidence_age":"audited-commit","verdict":"not-checked","blockers":[],"not_checked":["executed"],"snapshot_id":"sha256","commit_sha":"audited-sha","reviewer_id":"REV-1","signed_at":"ISO-8601","states":{"executed":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","reason":"nicht ausgefuehrt","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]},"result":{"value":"YES","evidence":[{"kind":"runtime-manifest","evidence_id":"EVID-001","run_id":"RUN-001","commit_sha":"audited-sha","timestamp":"ISO-8601"}]}},"overall_state":"not-checked"}
```

Alle 17 Achsen muessen vorhanden sein. Evidence ist Objekt, kein freier String.
Alternative Pfade teilen `feature_id`, besitzen verschiedene `path_id`.
`not_checked` entspricht exakt allen UNKNOWN-Achsen.
Runtimewerte referenzieren ausschliesslich existierende, hashvalidierte
`evidence_id` aus `runtime_runs.jsonl`.

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
und referenzielle Integritaet in temporaerem Ziel. Erst danach atomarer Rename
zum Masterledger. Fehler laesst vorheriges Masterledger byteidentisch. Director
editiert oder merged keine einzelnen Rangezeilen manuell.
