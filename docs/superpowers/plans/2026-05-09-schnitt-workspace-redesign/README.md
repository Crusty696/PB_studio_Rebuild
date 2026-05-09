# SCHNITT Workspace Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verschmelze die Top-Tabs `AUTO-SCHNITT` und `REVIEW` zu einem einzigen `SCHNITT`-Workspace mit Drei-Zustands-Architektur (Empty/Loading/Editor), vier Sub-Tabs, persistentem Inspector, Clip-Locking und persistenter Versionierung.

**Architecture:** `SchnittWorkspace` als `QStackedWidget` mit drei States. Der Editor-State ist ein `QTabWidget` mit den Sub-Tabs `Schnitt`, `Pacing & Anker`, `Audio`, `RL & Notes` plus persistentem `ClipInspectorPanel` als rechte Spalte. Datenarchitektur strikt UI ↔ Daten getrennt: `PacingProfile`-Dataclass + `TimelineState`-Dataclass + Hybrid-Undo (QUndoStack live + persistente `timeline_snapshots`). Neue DB-Tabellen `timeline_snapshots`, `project_notes` und neue Column `timeline_entries.locked`.

**Tech Stack:** PySide6 (Qt 6), SQLAlchemy + Alembic-style Migrations, pytest mit `QT_QPA_PLATFORM=offscreen`, conda-env `pb-studio` (Python 3.10, torch 1.12.1+cu113).

---

## Spec-Anker

Diese Phasen-Files folgen exakt der freigegebenen Spec:

`docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md`

Vault-Living-Plan (Pflichtlektüre vor jeder Sub-Task):

`C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`

## Phasen-Reihenfolge (Pflicht: nicht überspringen)

| # | Datei | Inhalt |
|---|---|---|
| 01 | [01_DB_MIGRATIONS.md](01_DB_MIGRATIONS.md) | `TimelineEntry.locked` Column, `TimelineSnapshot`-Tabelle, `ProjectNote`-Tabelle, Migrations-Skripte. |
| 02 | [02_DATA_SERVICES.md](02_DATA_SERVICES.md) | `PacingProfile`-Dataclass, `TimelineState`-Dataclass, `TimelineSnapshotService`, `ProjectNotesService`, `ui_binder`. |
| 03 | [03_BUILDING_BLOCKS.md](03_BUILDING_BLOCKS.md) | `WheelGuard`-EventFilter (Maus-Schutz), `LockIconItem`-QGraphicsItem. |
| 04 | [04_SCHNITT_SKELETON.md](04_SCHNITT_SKELETON.md) | `SchnittWorkspace`-Skelett mit drei Views, State-Manager, Empty-State-Detection. |
| 05 | [05_SUBTAB_SCHNITT.md](05_SUBTAB_SCHNITT.md) | Sub-Tab `Schnitt`: Preview + Transport + InteractiveTimeline + Clip-Locking + persistenter Inspector. |
| 06 | [06_SUBTAB_PACING_ANKER.md](06_SUBTAB_PACING_ANKER.md) | Sub-Tab `Pacing & Anker`: Pacing-Curve + Settings + Anker-Liste + Re-Generate-Confirm + Lock-aware-Service. |
| 07 | [07_SUBTAB_AUDIO.md](07_SUBTAB_AUDIO.md) | Sub-Tab `Audio`: Waveform + Beatgrid + Stems-Mixer + LUFS + Tonart. |
| 08 | [08_SUBTAB_RL_NOTES.md](08_SUBTAB_RL_NOTES.md) | Sub-Tab `RL & Notes`: 👍/👎 + RL-Event-Liste + Notes-Editor mit Auto-Save. |
| 09 | [09_WORKER_REFACTOR.md](09_WORKER_REFACTOR.md) | Worker-Stage-Progress-Signal, Loading-View-Hook. |
| 10 | [10_NAV_AND_INTEGRATION.md](10_NAV_AND_INTEGRATION.md) | `nav_bar` reduzieren, `workspace_setup` re-mappen, `cockpit_orchestrator` `open_schnitt`, QSettings-Migration. |
| 11 | [11_TESTS.md](11_TESTS.md) | Bestehende Tests anpassen, neue Tests ergänzen. |
| 12 | [12_CLEANUP_AND_VERIFY.md](12_CLEANUP_AND_VERIFY.md) | Legacy-Code löschen (`btn_toggle_inspector`, alter `EditWorkspace`); Live-Verifikation mit Test-Datensatz. |

## Pflicht-Regeln (für jede Sub-Task)

1. **Vault-Update:** Nach Abschluss jeder Task `projects/pb-studio/wiki/synthesis/schnitt-workspace-redesign-2026-05-09.md` Status fortschreiben (Sub-Task-Eintrag mit Datum + Commit-Hash).
2. **Sprache zum User:** Deutsch.
3. **Caveman-Mode:** aktiv. Code/Commits = normal, Status-Updates an User = caveman-knapp.
4. **`status: fixed`** vergibt nur der User nach Live-Test.
5. **Conda-Env:** `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe` für alle pytest-Aufrufe.
6. **Commit-Format:** Conventional Commits. Subject ≤50 Zeichen.
7. **TDD:** Test zuerst, fail beobachten, minimal-impl, pass beobachten, commit.

## Globaler Erfolgs-Test (Verifikation am Ende)

Nach Phase 12: User startet PB Studio, importiert Solo_Natur (103 Files) + Crusty Progressive Psy Set2.mp3, geht zu SCHNITT, sieht Empty-State, klickt „Techno"-Preset, sieht Loading mit rotierenden Texten, sieht Editor mit allen 4 Sub-Tabs + Inspector, sperrt einen Clip per Lock-Icon, drückt „Mit neuem Pacing generieren", bestätigt QMessageBox, sieht dass gesperrter Clip überlebt. Notes werden gespeichert und beim Re-Open wiederhergestellt.

## Tech-Anker (häufig gebraucht)

- Python: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`
- pytest:
  ```text
  "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest <path> -v --tb=short
  ```
- Vault: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`
- Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3 (149 MB DJ-Mix)
