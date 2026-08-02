# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
supplemental_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md
stability_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-076-stabilitaetsprogramm-current-head.md
live_test_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-085-beobachtete-live-test-session-vor-restfixes.md
updated: 2026-08-02
worktree: .worktrees/stab1-b727
branch: codex/B-727-stability-gate

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

`ROOT-CAUSE / B-757 Brain-Stats-Achszahl aus kanonischen Achsen ableiten`.

B-737 ist code-complete/live-pending: semantischer Timeline-Write vor
Pattern-Notifier, Debounce/Run-/Projekt-/App-End-Drain, generation-sicheres
Warten, Fehler-Retry und ehrliche Gewichte-Lernsession. Fokus 27 + 9 + 9
Tests gruen; Abschlussreview ohne Critical/High/Medium. B-757 wurde dabei als
getrennter Medium-Blocker reproduziert. B-738 wartet genau dahinter.

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
Nächste einzige Task: B-757, danach B-738.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
