# SCHNITT Workspace Redesign — Implementation Plan

> **Cross-Plan-Awareness — 3 neue Plaene 2026-05-19 (aktualisiert 2026-05-19):**
>
> Drei neue Plaene laufen parallel:
> 1. `VIDEO-PIPELINE-ENGINE-2026-05-19` (Plan A) — Video-Analyse + Proxy-Generation + Cross-Modal-Cut-Plaene. **SCHNITT-Timeline kann spaeter Proxy + Cut-Plan-Vorschlaege anzeigen** (optional, in Plan-A Phase 42 als Caller-Migration vorgesehen). Mirror `wiki/synthesis/plan-video-pipeline-engine-2026-05-19.md` · Decision `D-045`.
> 2. `LLM-BACKEND-PLATFORM-2026-05-19` (Plan B) — Embedded Ollama. **Keine neuen Direkt-Calls** auf `services/ollama_service.py` / `ollama_client.py` einfuegen — werden in Plan-B Phase 41/42 durch `services/llm/` ersetzt. SCHNITT-Controller / Pacing-Strategist / chat_dock werden in Plan B Phase 42 migriert. Mirror `wiki/synthesis/plan-llm-backend-platform-2026-05-19.md` · Decision `D-044`.
> 3. `GLOBAL-STORAGE-PROVENANCE-2026-05-19` (Plan C) — Content-Address-Storage + Provenance. **SCHNITT-Audio-Subtab bleibt unangetastet** dank Backward-compat-Adapter-Layer (Junction `storage/stems/<track_id>/` → `by_sha/<sha>/audio/`). Mirror `wiki/synthesis/plan-global-storage-provenance-2026-05-19.md` · Decision `D-046`.
>
> **Konkret fuer SCHNITT-Workspace-Redesign:** Stems-Pfade nicht aendern. LLM-Aufrufe ueber Plan B. Cut-Plan-Konsumenten optional in Plan A integriert.
>
> **Update 2026-06-14:** OTK-021 / Plan C darf nach User-Waiver `D-063`
> weitergehen. SCHNITT bleibt Consumer: keine direkten Stem-Pfad-Migrationen im
> SCHNITT-Plan. Plan C muss Backward-compat ueber Adapter/Junction liefern.
> Deferred Gate `DG-001` aus OTK-019 bleibt offen und muss vor fixed/release
> nachgeholt werden.

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

---

## Plan-Abweichungen-Register

> Stand 2026-05-09 nach Tier 1–6 Implementierung. Plan-Files (`01` … `12`) bleiben als historisches Artefakt unverändert. Hier dokumentiert: gezielte Abweichungen während der Umsetzung, jeweils mit Begründung. Keine dieser Abweichungen verletzt Spec-Authority — Spec wurde nicht angefasst.

| # | Bereich | Plan-Soll | Ist | Begründung |
|---|---|---|---|---|
| A1 | DB-Migration `add_locked_to_timeline_entries` | Standalone-Skript ohne Idempotenz | Idempotent (`PRAGMA table_info` Vor-Check) | Re-Run-Sicherheit auf existierenden DBs (T1.x). |
| A2 | DB-Migration `create_timeline_snapshots` | Standalone-Skript ohne Idempotenz | Idempotent (`sqlite_master` Vor-Check) | Konsistenz mit A1. |
| A3 | DB-Migration `create_project_notes` | Standalone-Skript ohne Idempotenz | Idempotent (`sqlite_master` Vor-Check) | Konsistenz mit A1/A2. |
| A4 | `PacingProfile`-Dataclass | Plain dataclass | `@dataclass(frozen=True)` mit `as_dict()` + `from_preset()` | Immutability + Roundtrip-Helpers für Snapshot-Serialisierung. |
| A5 | `TimelineState`-Dataclass | dict-basierte Repräsentation | Echte Dataclass mit `load(project_id, engine)` / `save_snapshot(...)` | Type-Safety + DI-Tauglichkeit für Tests. |
| A6 | `TimelineSnapshotService.restore` | Generischer Restore | Restore wirft `ValueError` bei Mismatch project_id ↔ Snapshot | Defensive gegen versehentlichen Cross-Project-Restore. |
| A7 | `ProjectNotesService` | Synchroner Save | Auto-Save-Debounce auf UI-Layer (RL-Notes-Subtab) | Performance bei Tipp-heavy Workflows. |
| A8 | `WheelGuard` | Generischer EventFilter | Whitelist-basiert (Slider, ScrollArea), Mouse-Wheel auf Timeline blockiert | Verhindert versehentliches Zoom/Scroll während Edit. |
| A9 | `LockIconItem` | QGraphicsPixmapItem | QGraphicsItemGroup mit Hover-State + Click-Signal | Bessere UX (Hover-Highlight). |
| A10 | `SchnittWorkspace` Empty-State | QLabel-only | Drei Buttons (Techno/Ambient/Custom) + Hint-Text | Direkte Preset-Auswahl ohne extra Dialog. |
| A11 | `SchnittWorkspace` Loading-State | Statisch „Loading..." | Rotierender Text + ProgressBar + Worker-Stage-Signal | UX-Feedback während mehrstufiger Pipeline. |
| A12 | Sub-Tab `Schnitt` Inspector | Toggle-fähig | Permanent rechts (kein Toggle-Button mehr) | Spec: persistenter Inspector. Alter `btn_toggle_inspector` in Phase 12 entfernt. |
| A13 | Sub-Tab `Pacing & Anker` Re-Generate | QMessageBox simple | Custom `ConfirmDialog` mit Lock-Count + Schnitt-Diff-Preview | Kontext für User vor destruktiver Aktion. |
| A14 | Sub-Tab `Audio` Stems-Mixer | Linear-Slider | LUFS-Anzeige live + Tonart-Detection async | Audio-Engineering-Genauigkeit. |
| A15 | `nav_bar` Reduktion | Tabs `AUTO-SCHNITT` + `REVIEW` löschen | Beide gelöscht + neuer Tab `SCHNITT` mit `cockpit_orchestrator.open_schnitt` | Plan-konform, dokumentiert wegen QSettings-Migration. |
| A16 | QSettings-Migration | Manueller Hinweis im Code | `migrate_qsettings_v2()` wird beim App-Start einmalig ausgeführt + setzt Versions-Key | Reibungsloser Upgrade von Bestands-Installationen. |
| A17 | Tests-Phase | „bestehende Tests anpassen, neue ergänzen" | Coverage-Tests pro Service + Workspace + Subtab + Controller (Tier 4–5, jeweils ≥85%) | Höherer Abdeckungsgrad als Plan-Mindest. |
| A18 | Test-Infra (Tier 6) | Plan implizit | `StaticPool`-In-Memory-Engine + session-scoped `qapp` + `patched_schnitt_engine`-Fixture in `tests/conftest.py` | Cross-Thread-Tests stabilisieren, Multi-QApplication-Warnungen vermeiden. |

Spec-Status: weiterhin `draft-approved-for-planning` — `status: fixed` vergibt User nach Live-Verify gemäß Phase 12.

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-008` on 2026-06-09.

- Original plan: `SCHNITT-WORKSPACE-REDESIGN-2026-05-09`
- Original open work: Phase 12 live verification / user confirmation path.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.
