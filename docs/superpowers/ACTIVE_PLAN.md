# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
supplemental_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md
stability_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-076-stabilitaetsprogramm-current-head.md
live_test_decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-085-beobachtete-live-test-session-vor-restfixes.md
updated: 2026-07-28
worktree: .worktrees/stab1-b727
branch: codex/B-727-stability-gate

## Why This Plan Is Active

User-Auftrag 2026-07-16: ALLE offenen Tasks aus allen fruehereren Plaenen +
Vault-Bugs in EINEN Master-Plan konsolidiert; 9 Herkunfts-Plaene per `superseded`
geschlossen (Entscheidung D-071, User-Wahl "Superseden"). Der Master ist ab jetzt
die einzige aktive Quelle offener Arbeit.

## Current Next Task

`LIVE-VERIFY / B-743 Settings-/Recent-Project-AppData-Isolation`.

B-715/B-723/B-725/B-726/B-735/B-736 sowie B-741 sind
code-complete/live-pending. B-737 wurde vor erstem Codeedit sauber gestoppt.
Userentscheidung D-085 priorisiert jetzt beobachtete Live-Workflows; User
schaut zu. B-737/B-738 bleiben offen und werden danach fortgesetzt.

Keine redundante breite Pytest-Suite. Live-Session nutzt isoliertes Projekt,
Click-/App-/DB-/GPU-/Prozessbelege. Erster reproduzierbare Fehler stoppt
aktuellen Workflow und öffnet genau eine Root-Cause-Task. B-278-Fix ist als
`1b2f161` integriert; sichtbarer Retry zeigte kohärent `Ollama` + `AI ready`,
der exakte Timeout-Race blieb nicht erzwungen. W1-Projektanlage gelang, schrieb
aber trotz isoliertem Launcher in echte
`%APPDATA%\PBStudio\settings.json`. B-743 ist `open`; W1 bleibt bis kleinstem
Root-Cause-Fix, Fokusbeweis und beobachtetem Live-Retry blockiert.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.
