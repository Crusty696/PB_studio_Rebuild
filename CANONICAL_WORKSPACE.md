# ⚠️ KANONISCHER ARBEITSORDNER — HIER arbeiten, sonst NIRGENDS

**Stand: 2026-06-24 (Konsolidierung nach Workspace-Fragmentierung)**

## Das ist der eine, echte Arbeitsordner

```
C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild
```

- Git-Remote: `origin` = https://github.com/Crusty696/PB_studio_Rebuild.git
- Aktueller Arbeitsbranch: `main` (Session-Pushes auf `session-2026-07-16-bugfixes`)
- App-Start: `start_pb_studio.bat` (conda-env `pb-studio`).
  Manueller GUI-Test mit Klick-Aufzeichnung: `start_pb_studio_clicklog.bat`.

## ❌ NICHT mehr verwenden (veraltete Duplikate / Backups)

Diese Orte sind **Altlasten** der Fragmentierung. NICHT dort entwickeln, NICHT `cd` hineinmachen:

1. `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild_github_compare`
   (alter GitHub-Klon + verlinkter Worktree; Inhalt nach #1 konsolidiert)
2. `C:\Users\David_Lochmann\.config\superpowers\worktrees\PB_studio_Rebuild\*`
   (superpowers-Worktrees; Inhalt nach #1 konsolidiert)

## Regel für Agenten

- IMMER zuerst prüfen: `git -C <ordner> remote -v` muss `Crusty696/PB_studio_Rebuild` zeigen
  und `git status` muss auf einem `codex/`- oder `main`-Branch stehen.
- Falls eine Aufgabe einen Worktree braucht: Worktree **unterhalb dieses Ordners**
  anlegen (`./.worktrees/<name>`), NIEMALS unter `%USERPROFILE%\.config\...`.
- Falls Code „woanders" auftaucht: STOP, mit User klären, nicht parallel weiterbauen.

## Sicherungen dieser Konsolidierung

- Git-Tags im Repo: `snapshot-master-pre-consolidation-20260624`,
  `snapshot-gemini-b549-pre-consolidation-20260624`.
- Lokale Branches `master` (alter Snapshot) und `gemini/B-549-stems-cancel-fix` bleiben erhalten.
- Alle Commits sind auf GitHub gepusht (Backup).
