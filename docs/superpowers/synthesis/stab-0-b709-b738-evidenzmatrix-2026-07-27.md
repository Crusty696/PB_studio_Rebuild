# STAB-0 — B-709 bis B-738 Evidenzmatrix

Datum: 2026-07-27
Baseline/Current HEAD:
`02cddee9e7e8dd50d1d45fdb67fc930de834805b`
Plan: `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16`
Decision: Vault `D-076-stabilitaetsprogramm-current-head.md`

## Verifikationsgrenze

STAB-0 änderte keinen Produktcode und startete keine pytest-Suite. B-727 ist
noch nicht als Vertrauensgate ausgeführt; deshalb wäre neue pytest-Evidenz vor
STAB-1 nicht belastbar. Current-Reproduktion bedeutet hier ausschließlich
statisch belegter Current-Codezustand. Historische Commit-Tests werden als
historisch benannt, nie als Current-Lauf verkauft.

## Matrix

| ID | Current Vault vorher | Commit(s) / Produktpfad | Historische RED/GREEN-/Regressionsevidenz | Livebeleg | Current-Befund | Zielstatus | Verbleibender Nachweis |
|---|---|---|---|---|---|---|---|
| B-709 | open | `62108eb`; `services/export_service.py` | Ruff F811 vorher rot, danach `ruff check .` + Import-Smoke grün | keiner | Fix vorhanden; kein Current-Lauf | code-fix-pending-live-verification | STAB-1 Ruff/Import + Vollsuite |
| B-710 | open | `3f0fdce`, `d9dcef0`; `ui/widgets/video_preview.py` | 4 Generations-Tests + 2 Follow-up-Tests; neutralisierte Guards rot | keiner | Fix und Error-/Lifetime-Follow-up vorhanden | code-fix-pending-live-verification | W5 Preview/Seek live, Worker-Lifetime |
| B-711 | open | `17fb939`; `start_pb_studio.py` | Launcher-Testdatei 4 grün; ohne Fix rot | keiner | Env-Invarianten vorhanden | code-fix-pending-live-verification | W1 echter Python-Launcher |
| B-712 | open | `17fb939`; `start_pb_studio.py` | wie B-711; Exitcode-Gegenprobe rot | keiner | Exitcode wird durchgereicht | code-fix-pending-live-verification | kontrollierter App-Fehler über Launcher |
| B-713 | open | `7110531`; `services/task_manager.py` | 5 Fokus; neutralisierte Registrierungen rot | keiner | terminale TaskInfo wird registriert | code-fix-pending-live-verification | W8 echter Start-/Shutdown-Fehlerpfad |
| B-714 | open | `6b9deac`; `ui/controllers/schnitt_controller.py` | 9 Fokus, 137 angrenzende UI; Guards neutralisiert rot | keiner | Projektgeneration-Guard vorhanden | code-fix-pending-live-verification | W1/W5 Projektwechsel während Workerabschluss |
| B-715 | open | kein Fixcommit; `ui/controllers/workspace_setup.py` | keine aktuelle Fixevidenz | keiner | **statisch reproduziert:** `_push_active_project_to_schnitt()` ruft `binder.refresh(pid)` und `nullpool_session()` synchron; Async-Helfer schützt nur `_update_workflow_gates()` | open | Root Cause + RED-Perf/Thread-Test, dann W5 |
| B-716 | open | `7c77243`; `ui/controllers/workspace_setup.py` | Ruff, py_compile, Offscreen-Import; kein pytest-Lauf im Commit | keiner | `visibilityChanged`-Sync vorhanden | code-fix-pending-live-verification | W1 Dock-X/Toggle live |
| B-717 | open | `6b9deac`; `ui/controllers/schnitt_controller.py` | Teil der 9 Fokus/137 Regression; Gegenprobe rot | keiner | Event-Turn-Dedup vorhanden | code-fix-pending-live-verification | W1/W5 Cockpit-SCHNITT live |
| B-718 | open | `02bb89a`; `services/beat_analysis_service.py` | 6 Hash-Tests; Spy beweist kein Load bei Mismatch | keiner | SHA-Pin vorhanden | code-fix-pending-live-verification | W3 echter gepinnter Modellload |
| B-719 | open | `02bb89a`; `services/graph/sigma_renderer.py` | 4 Escape-/SRI-Tests; Gegenprobe rot | keiner | Escape/SRI/Fehlerpanel vorhanden | code-fix-pending-live-verification | STAB-5 echter QWebEngine-Render online/offline |
| B-720 | open | `82dd17d`; Workflows, `pyproject.toml`, `services/release_readiness.py` | 13 Policy-Tests; 10 ohne Fix rot | keiner | Workflow ist ehrlich manuell/deaktiviert und runtime-korrigiert; Hosted Checkout bleibt ohne FFmpeg nicht baubar | code-fix-pending-live-verification | STAB-6 lokaler kompletter Build; Hosted-Workflow bleibt bewusst blockiert |
| B-721 | open | `27b7a10`; `database/session.py` | 4 Fokus B-721/B-722; neutralisierter Swap rot | keiner | Engine-Swap bei `create_all`-Fehler blockiert | code-fix-pending-live-verification | W1/W8 Projektwechsel-/Rollback live |
| B-722 | open | `27b7a10`; `services/audio_pipeline/checkpoint.py` | parallele Checkpoint-Gegenproben rot, Fix grün | keiner | RLock + Lockfile + eindeutige Tempdatei vorhanden | code-fix-pending-live-verification | W3 paralleler/cancel/retry Produktlauf |
| B-723 | open | Teilfix `37dafce`; `workers/audio.py`, `workers/video.py`, `services/video_analysis_service.py` | historischer Lock-Probe-Befund; RAFT-Release-Test deckt nur ModelManager-Slot | keiner | **statisch weiter offen:** normaler Video-Cleanup liegt im Batch-Lease, äußerer Exception-`finally` und Audio-`empty_cache()` liegen außerhalb | open | erzwungenes Interleaving + echter Audio-/Video-Exceptionpfad |
| B-724 | open | `7110531`; `services/task_manager.py` | 5 Fokus; neutralisierter Cancel-Vorrang rot | keiner | später Worker-Error überschreibt Cancel nicht | code-fix-pending-live-verification | W3/W4/W8 Cancel live |
| B-725 | open | kein Fixcommit; `workers/import_export.py` | historischer deterministischer Lock-Probe-Befund | keiner | **statisch reproduziert:** `BatchConvertWorker.run()` hält globalen Lock unabhängig von `copy`/CPU-Codec | open | Codec-Gate + Interleaving + echter Copy/CPU/NVENC-Lauf |
| B-726 | open | kein Fixcommit; `services/video_analysis_service.py` | keine Fixevidenz | keiner | **statisch reproduziert:** öffentliche `compute_motion_scores()` lädt RAFT unter Load-Lock, inferiert/cleant ohne Execution-Lease; Batchcaller schützt nur Außenpfad | open | Direktpfad-Lease oder belegte interne Einschränkung + Interleaving |
| B-727 | open | `67664e3`, `dcd9a6b`, `42c7b56`, `c26a97d`, `32088fd`; `tests/conftest.py` | Shadowing-RED, beide sqlite-Namen, 0 Originalcalls, Collection/Subprozess/APP_ROOT; collect-only 2662 + 37/92 Fokus historisch | kein App-Live; Testschutz ist Testinfrastruktur | finaler Guardcode vorhanden; nach letztem Commit keine Current-Vollsuite | code-fix-pending-live-verification | STAB-1 Negativkontrollen + DB-Manifest + Vollsuite zweimal |
| B-728 | code-fix-pending-live-verification | `0574240`; `services/pacing_beat_grid.py` | 37 Fokus; read-only DB-Proof zeigt echte Tags beim Scorer | read-only Produkt-DB, kein App-Workflow | Wiring vorhanden | code-fix-pending-live-verification | W6 Auto-Edit Current-live |
| B-729 | open | `a84a880`, Merge `42948e1`; Enrichment-Classifier/Worker/Migration | 82 Enrichment-Tests; DB-Kopie 27 Szenen mit Rollen-/Confidence-Varianz | DB-Kopie/read-only, kein App-Reanalysepfad | SigLIP-Prototypen ersetzen stillen Filler-Fallback | code-fix-pending-live-verification | W4 Reanalyse + W6 Ranking live |
| B-730 | code-fix-pending-live-verification | `61cb640` (falsch als B-707 benannt); Pacing-Reranker/Pattern-Prior | `test_b707_per_clip_signal_variance.py`; neutralisierte Prior rot | keiner | Pattern-Prior vorhanden | code-fix-pending-live-verification | STAB-3 echte persistierte Patterns |
| B-731 | code-fix-pending-live-verification | `37b840e` (falsch als B-707 benannt); `services/brain/embedding_scheduler.py` | Cache-Hit-/Invalidierungsfokus; read-only Cache-Kopie | kein zweiter App-Import | Lookup-Gates vorhanden | code-fix-pending-live-verification | W2/W4 zweiter Import/Analyse live |
| B-732 | open | `2ee5ed8`; `services/brain/brain_v3_service.py` | Lernkreis-Fokus: Contributions/Diagnostik; Gegenprobe im Commit | keiner | Contributions werden durchgereicht | code-fix-pending-live-verification | STAB-3 Achsenwirkung A/B live |
| B-733 | open | `2ee5ed8`; Timeline-State, LearningDialog | Kontext-Fokus mit Struktur/BPM/Mood | keiner | echter CutContext wird aufgebaut | code-fix-pending-live-verification | STAB-3 Dialogfeedback + Neustart |
| B-734 | open | `fa85a27`; Pacing-Loader/Bridge/Reranker/Scorer | 15 Varianztests; alle ohne Fix rot; zwei read-only DB-Gegenproben | kein Auto-Edit-Live | Bildmetriken erreichen Ranking | code-fix-pending-live-verification | W6/STAB-3 Rankingvarianz live |
| B-735 | open | Commit `fa85a27` nennt ID, erfüllt Bug-DoD aber nicht; `services/brain/reranker.py`, `bridge_dimensions.py` | Tests belegen Pacing-Confidence, nicht Brain-Rollenachse | keiner | **statisch reproduziert:** Rolle landet nur in `style_tags`; keine Bridge-Achse liest `style_tags` | open | Produktentscheidung Mapping/No-Signal + Rollen-only-Varianztest |
| B-736 | open | Commit `fa85a27` nennt ID, ändert `BrainV3Service.suggest()` nicht | Musik-Snapshot-Tests sind fachfremd zum Service-Stub | keiner | **statisch reproduziert:** `_build_service_candidates()` erzeugt Score/Motion/Visuals weiter aus Index/Defaults; `brain_weight=1.0` | open | echter Kandidatenpfad oder Stub aus Produktfluss entfernen |
| B-737 | open | Teilfix `2ee5ed8`; `workers/memory_updater.py`, `brain_v3_service.py` | Tests nutzen `_CountingAggregator`; prüfen Debounce/Notifier, nicht echte Patternpersistenz | keiner; reale geprüfte DBs hatten `mem_learned_pattern=0` | **weiter offen:** Brain-Feedback notifiziert Aggregator, erzeugt aber keinen belegten `mem_decision`-Input; kein Test „1 Feedback → Pattern → Neustart“ | open | Root Cause + echte DB-/Neustart-A/B-Persistenz |
| B-738 | open | Teilfix `2ee5ed8`, `d9dcef0`; Knowledge/LocalAgent/ask_ai/Pacing | Prompt-/Call-Capture-Fokus; Toolless Prompt enthält Recall | keiner; Ollama beim Recon nicht erreichbar | **weiter offen:** Vision/Caption bewusst ausgeschlossen; modellunabhängige Recall/Stats/Explain/Learn-Wirkung über alle geforderten Pfade nicht bewiesen | open | Vertragsentscheidung Vision + echter ChatDock/Ollama Tool-/Non-Tool-Livebeweis |

## ID-Prüfung

Vaultweit `^id:\s*B-738$`, `^bug_id:\s*B-738$` und alle Bug-Frontmatter
geprüft:

- genau eine B-738-Datei:
  `B-738-brain-memory-nicht-fuer-alle-llm-pfade-erreichbar.md`;
- keine doppelte Bug-ID;
- höchste kanonische ID: B-738;
- keine Umnummerierung nötig;
- keine Datei gelöscht.

Die im Auftrag erwartete Duplicate-Klasse existiert im Current Vault nicht.
Eine künstliche Umnummerierung wäre falsch.

## Ergebnis

- 22 Bugs: `code-fix-pending-live-verification`.
- 8 Bugs: `open`.
- 0 Bugs: durch STAB-0 auf `fixed` gesetzt.
- 0 doppelte IDs.
- Genau nächste Task nach Governance-Commit:
  `STAB-1 / B-727 Vertrauensgate`.
