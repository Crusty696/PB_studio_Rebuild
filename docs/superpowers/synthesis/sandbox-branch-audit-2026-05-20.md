# Sandbox Branch Audit 2026-05-20

Status: `read-only-audit`

Scope:
- `sandbox/audio-analysis-v2`
- `sandbox/ux-redesign-2026-05-17`

Nicht gemacht:
- Kein Merge.
- Kein Rebase.
- Keine Sandbox-Dateien geloescht.
- Keine untracked Artefakte bereinigt.
- Keine Tests gestartet.

## Aktueller Haupttree-Hinweis

Der Haupttree `feat/video-pipeline-engine-2026-05-19` war vor diesem Audit nicht sauber. Geaendert waren Brain-V3-Plan-Dokumente unter `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/`. Diese Aenderungen wurden in diesem Audit nicht gelesen, nicht geaendert und nicht bewertet.

## `sandbox/audio-analysis-v2`

HEAD:
- `6f414dd2deb412ce1d5ce38c96279c732371731c`
- `audio-v2-strict: P5+P6+P7+P8 complete (43 tests GREEN, total 117 P1-P8)`

Worktree-Status:
- Nicht sauber.
- Geaendert: `_sandbox_meta/plan.md`.
- Sehr viele untracked Runtime-/Projektartefakte unter `hjgj/storage/keyframes/`, `hjgj/storage/proxies/`, `hjgj/storage/stems/`, plus `_sandbox_meta/app_data/PBStudio/settings.json` und `pb_project_meta.json`.

Code-Ideen:
- Neue strict-sequential Audio-Pipeline unter `services/audio_pipeline/`.
- Pipeline-Checkpointing, Resume, Cleanup, Stem-Cache, VRAM-Guard.
- `services/stem_router.py`.
- `services/av_pacing_service.py`.
- Aenderungen an Audio-/Beat-/Key-/Structure-Services.
- Worker-Registry/-Audio-Worker-Anbindung.
- Viele fokussierte Service-Tests.
- Zwei neue UI-Widgets:
  - `ui/widgets/pipeline_progress_panel.py`
  - `ui/widgets/project_save_button.py`

GUI/Tabs-Risiko:
- Keine grosse Workspace-/Tab-Umstrukturierung im Audio-Sandbox-HEAD gefunden.
- UI-Anteil ist aber vorhanden: Pipeline-Progress-Panel und Save-Button.
- Diese Widgets sind neue Oberflaechenflaechen und duerfen nicht blind in die aktuelle GUI gehoben werden.

Merge-Lage gegen aktuellen Branch:
- `git merge-tree --write-tree feat/video-pipeline-engine-2026-05-19 sandbox/audio-analysis-v2` meldet Konflikt in `services/perf_watchdog.py`.
- `services/project_manager.py` wird auto-gemerged, muss aber fachlich geprueft werden, weil Save/Auto-Save Teil der Audio-V2-Idee ist.

Bewertung:
- Wertvoller Branch, nicht loeschen.
- Nicht direkt mergen.
- Beste Strategie: Audio-Pipeline-Ideen in eigenen Plan-Reconcile uebernehmen, ohne Runtime-Artefakte und ohne UI-Widgets automatisch zu aktivieren.

## `sandbox/ux-redesign-2026-05-17`

HEAD:
- `67ec0356fb8654ab3e572a8e6c5bfac93643e00a`
- `sandbox(ux-redesign): 4 P0 UX-Fixes (PROP-001/002/004/015)`

Worktree-Status:
- Nicht sauber.
- Viele untracked Runtime-/Projektartefakte unter `tests/testtttt/storage/keyframes/`, `tests/testtttt/storage/proxies/`, `tests/testtttt/storage/stems/`, plus `_sandbox_meta/app_data/PBStudio/settings.json`.

Code-Ideen laut Commit:
- PROP-001: Stems-Player als ausklappbares Panel im Audio-Side-Panel von Material.
- PROP-002: versteckte Sub-Tab-Funktionen sichtbar machen (`btn_clear_all`, `btn_auto_duck`).
- PROP-004: Export-Vorschau und Protokoll als sichtbare Deliver-Tabs.
- PROP-015: RL-Feedback-Buttons sichtbar machen.

GUI/Tabs-Risiko:
- Hoch. Der Branch aendert direkt:
  - `ui/controllers/workspace_setup.py`
  - `ui/workspaces/deliver_workspace.py`
  - `ui/workspaces/edit_workspace.py`
  - `ui/workspaces/media_workspace.py`
  - `tests/ui/test_workspaces_smoke.py`
- Das bestaetigt den User-Befund: der Agent hat GUI/Tabs angefasst.

Merge-Lage gegen aktuellen Branch:
- `git merge-tree --write-tree feat/video-pipeline-engine-2026-05-19 sandbox/ux-redesign-2026-05-17` meldet:
  - `CONFLICT (modify/delete): ui/workspaces/edit_workspace.py deleted in feat/video-pipeline-engine-2026-05-19 and modified in sandbox/ux-redesign-2026-05-17`.
- Ursache: aktueller Branch hat die SCHNITT-UI inzwischen auf `ui/workspaces/schnitt_workspace.py` und `ui/workspaces/schnitt/*` umgebaut; der Sandbox-Branch basiert auf alter `edit_workspace.py`.

Bewertung:
- Nicht mergen.
- Ideen einzeln extrahieren.
- PROP-001/002/004 koennen als UX-Ideen weiterleben, muessen aber gegen aktuelle SCHNITT-/Workspace-Struktur neu geplant werden.
- PROP-015 ist besonders riskant, weil RL-Feedback in alter `edit_workspace.py` aktiviert wurde; aktuelle Struktur muss erst zeigen, wo diese Controls heute leben oder ob sie ueberhaupt noch valide sind.

## Runtime-Artefakt-Problem

Beide Sandbox-Worktrees enthalten viele untracked generierte Medien:
- Keyframes `.jpg`
- Proxy-Videos `.mp4`
- Stems `.wav`
- lokale Settings
- Projekt-Metadaten

Bewertung:
- Nicht in Git aufnehmen.
- Vor weiterer Arbeit `.gitignore`/Sandbox-Cleanup-Regel fuer diese Pfade klaeren.
- Vor Loeschen User-OK einholen, weil es echte Testdaten/Outputs sein koennen.

## Empfehlung

1. Beide Sandbox-Branches behalten.
2. Beide als `blocked-needs-reconcile` markieren.
3. Zuerst `sandbox/audio-analysis-v2` fachlich retten:
   - Nur `services/audio_pipeline/*`, `stem_router`, Service-Anpassungen und Tests einzeln portieren.
   - UI-Widgets erst spaeter, wenn Pipeline-Status-UX bewusst geplant ist.
4. Danach `sandbox/ux-redesign-2026-05-17` als Ideenkatalog behandeln:
   - Kein Branch-Merge.
   - PROP-001/002/004/015 einzeln gegen aktuelle UI neu bewerten.
5. Untracked Runtime-Artefakte separat klassifizieren:
   - behalten als Testdataset,
   - nach externen `storage/`/`outputs/` verschieben,
   - oder nach User-OK loeschen.

## Harte Stop-Regel

Kein Agent darf aus diesen Sandbox-Branches GUI-/Tab-Aenderungen direkt uebernehmen. Jede UI-Idee braucht:
- aktuelles Ziel-File im heutigen Branch,
- eigene Plan-Task,
- Screenshot-/Live-Smoke,
- und klare User-Freigabe.
