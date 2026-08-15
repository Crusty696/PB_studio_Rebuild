# Ledger-Schema

## files.jsonl

```json
{"run_id":"RUN-001","snapshot_id":"sha256","origin":"git","commit_sha":"git-sha","path":"services/x.py","git_mode":"100644","git_object_type":"blob","git_blob":"blob-sha","sha256":"file-sha","bytes":123,"media":"text","encoding":"utf-8","eol":"lf","line_count":10,"category":"runtime_product","generated_candidate":false,"lfs_pointer":false,"disposition":"direct-review","exclusion_id":null}
```

`media`: `text | binary | gitlink`. `disposition`: `direct-review | excluded-approved`.
Keine Exklusion ohne `exclusion_id` und separates, vom User genehmigtes Ledger.

`snapshot_id` wird aus allen Records ohne deren `snapshot_id` neu berechnet.
Inventory stammt aus HEAD-Tree/Blobs, nie aus gemischten Workingtree-Bytes.

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

## line_ranges_pass_a.jsonl / pass_b

```json
{"run_id":"RUN-001","snapshot_id":"sha256","pass":"A","reviewer_id":"agent-id","path":"services/x.py","file_sha256":"file-sha","start_line":1,"end_line":10,"range_sha256":"optional","checks":{"semantics":"done","errors":"done","state":"done","threading":"done","io_db_gpu":"done","wiring":"done"},"finding_ids":[],"verdict":"reviewed","signed_at":"ISO-8601"}
```

Ranges pro Datei: Start 1, Ende EOF, keine Luecke/Ueberlappung. Pass A/B Reviewer
verschieden. Datei-SHA muss Inventory und Current-Workspace entsprechen.

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

## feature_states.jsonl

```json
{"run_id":"RUN-001","feature_id":"FEAT-001","path_id":"preview","name":"Videoanalyse starten","user_surface":"ui","trigger":"button","handler":"ui/x.py:10","service":"services/x.py:20","worker":"N-A","state_store":"database/models.py:1","config_keys":[],"expected_result":"Analyse sichtbar","evidence_age":"current-head","verdict":"not-checked","blockers":[],"not_checked":["executed"],"snapshot_id":"sha256","commit_sha":"git-sha","reviewer_id":"agent-id","signed_at":"ISO-8601","states":{"executed":{"value":"UNKNOWN","evidence":[{"kind":"not-checked","ref":"RUN-MISSING","reason":"nicht ausgefuehrt","run_id":"RUN-001","commit_sha":"git-sha","timestamp":"ISO-8601"}]}},"overall_state":"not-checked"}
```

Alle 17 Achsen muessen vorhanden sein. Evidence ist Objekt, kein freier String.
Alternative Pfade teilen `feature_id`, besitzen verschiedene `path_id`.
`not_checked` entspricht exakt allen UNKNOWN-Achsen.

## Completion

Universum: jede Textzeile + Metadateneinheit pro Datei + Inhalts-/Integritaetseinheit
pro Binaerdatei. Abschluss nur bei clean Snapshot, identischen Hashes, Pass A/B
lueckenlos, verschiedenen Reviewern, vollstaendigen Nicht-Zeilen-Einheiten,
genehmigten Exklusionen, allen Feature-IDs und beiden Validatoren Exit 0.
