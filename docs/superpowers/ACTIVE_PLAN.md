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

`ROOT-CAUSE / B-751 Audio-V2 User-Cancel als cancelled statt error/Erfolg`.

B-715/B-723/B-725/B-726/B-735/B-736 sowie B-741 sind
code-complete/live-pending. B-737 wurde vor erstem Codeedit sauber gestoppt.
Userentscheidung D-085 priorisiert jetzt beobachtete Live-Workflows; User
schaut zu. B-737/B-738 bleiben offen und werden danach fortgesetzt.

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
bewiesen. W3-Cancel stoppte AV-Pacing kooperativ bei Chunk 1; aktueller Defekt:
Worker/AnalysisStatus behandeln User-Cancel als `error`/`Worker-Fehler` und der
Komplett-Controller kann danach Erfolgstext schreiben. B-751 blockiert Retry.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
