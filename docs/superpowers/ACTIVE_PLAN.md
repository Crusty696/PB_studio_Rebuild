# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
supplemental_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md
stability_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-076-stabilitaetsprogramm-current-head.md
live_test_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-085-beobachtete-live-test-session-vor-restfixes.md
current_sequence_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-089-agy-rest-vor-b758.md
updated: 2026-08-12
worktree: C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild
branch: main

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

`ROOT-CAUSE / B-820 Cancel-Status wird vom Status-Reconciler auf done
überschrieben`. Danach W3 fortsetzen mit Retry, Neustartvergleich und
fehlendem Stem.

W3-Live-Session 2026-08-14, Run `20260814T0405-w3-audio-v2` auf HEAD `22f96b8`:
App-Start, Systemcheck, Projekt-Load im isolierten Scope, Fehlerpfad bei
fehlender Audio-Quelldatei, Cancel-Mechanik und Shutdown sind live pass.
Pre- und Post-Manifest `pass`, alle fünf Host-/Repo-DBs byte-identisch,
0 Prozessreste. B-758 ist damit erstmals in dieser Session selbst live belegt
(CUDA available true, GTX 1060 6143 MB, kein FAIL-Modal); `fixed` bleibt
Userrecht.

Gestoppt nach Erste-Fehler-Regel durch neuen Bug B-820: ein per User-Cancel
abgebrochener Analyse-Schritt wird in derselben Sekunde vom Status-Reconciler
(`_ensure_status_done`, `services/analysis_status_service.py:750-754`) wieder
auf `status='done'` gesetzt, `error_message` wird gelöscht. Der B-751-Cancel-
vertrag überlebt den nächsten Status-Refresh nicht. Kein Code angefasst.
Details: `docs/superpowers/synthesis/functional-test-w3-audio-v2-2026-08-14.md`
und Vault `wiki/bugs/B-820-*.md`.

AGY-Rest gemaess D-089 ist mit getrennten Commits und ehrlichen Live-Grenzen
abgeschlossen. B-817 und B-818 wurden als direkte AGY-Regressionen repariert;
`fixed` bleibt Userrecht. B-758-Systemcheck ist im exakten isolierten W3-
Harness gruen. B-819 wurde in Commit `532165f` korrigiert: 4 Fokus-Tests,
Syntax/Ruff, isolierter Zwei-`init_db()`-Lauf und sichtbarer App-Manifestlauf
`20260812T1354-b819-live-manifest` sind gruen; geschuetzte Bootstrap-DB vor/
nach byte-, schema- und logisch identisch. `fixed` bleibt Userrecht. B-758-
Manifest-Recheck damit pass; naechste einzige Task ist W3-Fortsetzung.

W3 wurde am Current HEAD `e85a2c2` vor jeder Projektöffnung gestoppt: modaler
Systemcheck meldete `CUDA GPU FAIL` und `NVENC Encode FAIL`; degradierter Start
wurde nicht gewählt. Screenshot und Pre-/Post-Manifeste vorhanden. Repo-Root-
WAL/SHM-Drift wurde extern gesichert und recoverable bereinigt. W3 bleibt 25 %;
Fortsetzung erst nach B-758 Root Cause, kleinstem Fix und Current-Livebeweis.

B-737 ist code-complete/live-pending: semantischer Timeline-Write vor
Pattern-Notifier, Debounce/Run-/Projekt-/App-End-Drain, generation-sicheres
Warten, Fehler-Retry und ehrliche Gewichte-Lernsession. Fokus 27 + 9 + 9
Tests gruen; Abschlussreview ohne Critical/High/Medium. B-757 leitet Schema-
und UI-Grenze jetzt aus 18 kanonischen Achsen ab; Fokus und Review gruen,
App-Livebeweis offen. B-738 ist code-complete/live-pending: sicherer Tool-/
Non-Tool-Gateway, reservierter Learn-Control-Prefix und read-only Vision-
Recall/Explain sind fokussiert gruen. Damalige Folgetask war W3-Liveverify.

Keine redundante breite Pytest-Suite. Live-Session nutzt isoliertes Projekt,
Click-/App-/DB-/GPU-/Prozessbelege. Erster reproduzierbare Fehler stoppt
aktuellen Workflow und öffnet genau eine Root-Cause-Task. B-743 `b0aac7e` und
B-744 `ebc6546` sind live bewiesen: Session-Settings/RecentProjects isoliert,
null QSettings-Migration, Host-JSON und 15 geschützte DBs unverändert. Beide
bleiben ohne Usermarker `code-fix-pending-live-verification`. W1 ist
Current-live bestanden, Usermarker offen. B-745 war
UI-Automations-Schließartefakt; zwei native Windows-Schlüsse ohne Fatal,
kein Produktcodefix. W2-Preflight fand die festgelegten 20 Clip-Fixtures nicht:
Provenienzpfade zeigen auf ein nicht vorhandenes Altprofil. D-086 akzeptiert
deshalb 20 deterministisch ausgewählte MP4-Proxies plus zwei WAV-Stems als
ausschließlich isolierte Kopien. Quellen bleiben read-only.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

W2 Import, Duplikat, Papierkorb, Bulk-Restore, Reimport und Cross-Project-Reuse
sind Current-live grün. B-747 wurde minimal behoben und live belegt. B-740-
Owned-Tree-Cleanup wurde mit echter App→Serve→Runner-Kette und nativem Shutdown
bewiesen. Finalmanifest: reale DBs/Settings unverändert, PB-/Ollama-Prozesse 0.
W2 live-pass, Usermarker offen. W3-Komplettlauf mit vier Stems ist bereits
Teilevidenz; offen bleiben Cancel, Retry, Neustartvergleich und fehlendes Stem.
B-748 Incident beim W3-Start ist recovered und Current-live geschlossen:
Fail-Closed-Stability-Scope blockierte absichtlichen Host-Projektversuch vor
DB-Zugriff; 6/6 geschuetzte Pre-Pfade blieben unveraendert. Usermarker offen.
W3 wird ausschließlich mit `gui_harness.py start --stability-project ...`
fortgesetzt.
B-752 None-Summary-Crash wurde im echten Resume-Pfad behoben und Current-live
bewiesen. B-751 ist Code+Current-live abgeschlossen: AV-Pacing stoppt bei
Chunk 1, Task bleibt `cancelled`, persistierter Retry-Vertrag ist
`status=error/error_message=cancelled`, kein Worker-ERROR und kein falscher
Batch-Erfolg. 13 Fokustests, Syntax/Ruff, Host-DB-Manifeste und isolierter
Runtime-Quickcheck gruen; Usermarker offen. B-753 Pre-Start-Cancel ist
code-complete: RED→GREEN, 15 fokussierte B-753/B-751/B-724-Tests,
Syntax/Ruff sowie echter QThread-Interleaving-Beweis grün. Terminalsignal und
Threadende binnen 2 s belegt; App-GUI-Liveklick/Usermarker offen. Nächste
Root-Cause-Task ist B-750. B-754 (stale `completed_at` nach Cancel) bleibt
eigener offener Bug.

B-750-Follow-up ist code-complete: Canceltext ehrlich; Audio-Retry-all startet
einen resumierbaren Strict-Sequential-Worker; Onset resettiert/läuft
`stem_gen` zur Artefakt-Selbstheilung; zentraler Dispatcher-Claim schützt
Einzel-V2, Batch-V2, Retry und kollidierende StemSeparation pro Projekt/Track.
Release erfolgt erst im QThread-Cleanup. Review-RED 5/5 plus Cross-Path-RED
3/3; final 27 fokussierte B-750/Dispatcher/B-751/B-222-Tests sowie
Syntax/Ruff grün. App-GUI-/Medien-Livebeweis bleibt gebündelt für W3 offen.
Stand-6-Follow-up schließt Re-Review-Lücken: Full-/Batch-V2-/Stem-Cancel und
`Bereits aktiv` werden ehrlich getrennt; Claim-Release deckt frühe Setup-,
Shutdown-, terminal/no-thread- und Fast-Finish-Pfade ab. Final 65 direkte
Lifecycle-/B-750-Regressionen, Syntax, Ruff und Diff-Check grün;
unabhängiger Abschlussreview PASS ohne Critical/High/Medium. B-750 bleibt
`code-fix-pending-live-verification`, weil App-GUI-/Medienbeweis W3 offen ist.
Nächste einzige Task: B-755.

B-754 ist code-complete: Done→Started→Cancel löscht stale `completed_at` im
zentralen `mark_cancelled()`-Conflict-Update. RED→GREEN; drei direkte
Cancel-/Idempotenzverträge, Syntax, Ruff und Diffcheck grün. App-/DB-Live-Retry
bleibt W3. Parallel-Mapping erfasste B-755 (`running` behält Altzeit) und
B-756 (Video-Cancel via `mark_error("cancelled")`) als getrennte Bugs.

B-755 ist code-complete: `mark_started()` löscht stale `completed_at` beim
Übergang Done→Running. RED→GREEN; drei direkte Transitionstests, Syntax, Ruff
und Diffcheck grün. Live-Sichtung bleibt W3.

B-756 ist code-complete: sieben Video-`should_stop()`-Zweige nutzen den
kanonischen `mark_cancelled()`-Vertrag; echte Exceptions bleiben
`mark_error()`. RED 7/7, zwei direkte Routing/Timestamp-Verträge, Syntax, Ruff
und Diffcheck grün. Video-Live-Cancel bleibt W4. Gemäß Uservorgabe breite/live
Tests erst nach Codeaufgaben.

B-737 ist code-complete: ein semantisches Brain-Timeline-Rating schreibt
`mem_decision.user_rating`, plant Pattern-Aggregation und persistiert nach
DB-Neustart; Feedback unter 20 Events flusht per Debounce/Lifecycle. Shutdown
drainiert Nachfolgegenerationen, Best-Effort kann nicht endlos loopen.
Gewichte-Lernsession ist mangels autoritativer Run-/Scene-Verknuepfung ehrlich
separat. Kein App-Livebeweis, daher `code-fix-pending-live-verification`.
B-757 ist code-complete/live-pending: `BRIDGE_AXIS_COUNT` bindet Stats-Schema,
Label und Progressbar an `BRIDGE_AXES`; sechs Kernbelege plus verschaerfter
18/19-Grenztest, Ruff, Compileall und Diffcheck gruen. Abschlussreview ohne
Critical/High/Medium.

B-738 ist code-complete/live-pending: echter Orchestrator-Tool-/Non-Tool-Pfad
erhaelt projektisolierten Recall. Non-Tool-Aktionen brauchen eindeutigen
`pb_brain_gateway=v1`-Envelope; persistentes Learn zusätzlich reservierten
User-Prefix mit Doppelpunkt. Vision erhaelt Recall-Miss-Fallback und neueste
Cut-Erklaerung read-only, Fachprompt bleibt letzte Anweisung. Fokus 44 Tests,
Learn-Recall-Kreis, Ruff, Compileall und Diffcheck gruen; Abschlussreview ohne
Critical/High/Medium. Kein ChatDock-/Ollama-/Neustart-Livebeweis. Naechste
einzige Task: `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes
Stem`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
