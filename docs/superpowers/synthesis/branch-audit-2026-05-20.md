# Branch Audit 2026-05-20

Status: `audited-read-only`

Scope:
- Geprueft: alle lokalen und sichtbaren Remote-Branches ausser `sandbox/audio-analysis-v2` und `sandbox/ux-redesign-2026-05-17`.
- Nicht gemacht: keine Branch-Loeschung, kein Merge, kein Rebase, keine Testlaeufe pro Branch.
- Basis nach `git fetch --prune origin`: aktueller Branch `feat/video-pipeline-engine-2026-05-19` bei `eeeaf0d1a723be139e1e6cacb4a84f56fcf9b656`.

## Kurzbefund

Der aktuelle Branch ist sauber. Die alten SCHNITT-Backup-/Feature-Branches sind vollstaendig im aktuellen Branch enthalten und damit stale/dupliziert. `codex/bug-task-list-2026-05-07` ist nicht enthalten und verursacht beim Merge in den aktuellen Branch einen echten Konflikt in `ui/controllers/media_table.py`. `origin/main` und `origin/workflow/auto-merge-cleanup` enthalten GitHub-Actions-Auto-Merge-/Cleanup-Workflows; sie sind technisch konfliktfrei, aber governance-riskant, weil sie PRs automatisch mergen und Branches loeschen koennen.

## Branches

| Ref | HEAD | Relation zum aktuellen Branch | Merge in aktuellen Branch | Befund |
|---|---:|---|---|---|
| `feat/video-pipeline-engine-2026-05-19` | `eeeaf0d1` | identisch | nicht noetig | Aktiver Arbeitsbranch, sauber. |
| `main` | `3a9a7165` | 141 Commits hinter aktuellem Branch, 0 eigene | konfliktfrei/no-op | Lokal stale; aktueller Branch enthaelt `main`. |
| `origin/main` | `441475e3` | 141 hinter / 1 voraus | konfliktfrei | Enthaltene Aenderung: `.github/workflows/auto-merge.yml`. Nicht blind uebernehmen. |
| `origin/workflow/auto-merge-cleanup` | `506bc769` | 141 hinter / 2 voraus | konfliktfrei | Fuegt Auto-Merge- und Branch-Cleanup-Workflows hinzu. Governance-Risiko. |
| `feat/schnitt-redesign-2026-05-09` | `1af205ed` | 10 Commits hinter / 0 voraus | konfliktfrei/no-op | Vollstaendig im aktuellen Branch enthalten; stale. |
| `origin/feat/schnitt-redesign-2026-05-09` | `1af205ed` | 10 Commits hinter / 0 voraus | konfliktfrei/no-op | Identisch zur lokalen SCHNITT-Feature-Branch; stale. |
| `backup/schnitt-redesign-2026-05-11` | `ed9be02f` | 22 Commits hinter / 0 voraus | konfliktfrei/no-op | Vollstaendig im aktuellen Branch enthalten; stale. |
| `backup/schnitt-redesign-2026-05-11-v2` | `ed9be02f` | 22 Commits hinter / 0 voraus | konfliktfrei/no-op | Exaktes Duplikat von `backup/schnitt-redesign-2026-05-11`; stale. |
| `codex/bug-task-list-2026-05-07` | `0a370ec4` | 141 hinter / 1 voraus | Konflikt | Enthaltener Bugfix `fix(B-282): select real auto-edit media`; Konflikt in `ui/controllers/media_table.py`. |
| `feat/audio-analysis-v2` | `12db3784` | 141 hinter / 5 voraus | konfliktfrei laut merge-tree | Nicht in aktuellem Branch enthalten; enthaelt Audio-Pipeline-/Sandbox-Metadaten. Vor Integration Plan-/Runtime-Pruefung noetig. |

## Konflikte

### `codex/bug-task-list-2026-05-07`

`git merge-tree --write-tree feat/video-pipeline-engine-2026-05-19 codex/bug-task-list-2026-05-07` meldet:

```text
CONFLICT (content): Merge conflict in ui/controllers/media_table.py
```

Betroffene Commit-Dateien:
- `services/task_manager.py`
- `tests/test_services/test_b222_signal_queued_connections.py`
- `tests/ui/test_director_combo_readiness.py`
- `ui/controllers/media_table.py`
- `ui/controllers/workspace_setup.py`

Bewertung: nicht loeschen, bevor geprueft ist, ob B-282 im aktuellen Branch bereits funktional enthalten ist. Wenn nicht enthalten, gezielt cherry-picken oder manuell portieren, nicht blind mergen.

## Stale / Duplikate

Stale und vollstaendig im aktuellen Branch enthalten:
- `backup/schnitt-redesign-2026-05-11`
- `backup/schnitt-redesign-2026-05-11-v2`
- `feat/schnitt-redesign-2026-05-09`
- `origin/feat/schnitt-redesign-2026-05-09`
- lokales `main` als Basisbranch

Exaktes Duplikat:
- `backup/schnitt-redesign-2026-05-11`
- `backup/schnitt-redesign-2026-05-11-v2`

## Remote-Workflow-Risiko

`origin/main` fuegt `.github/workflows/auto-merge.yml` hinzu.

`origin/workflow/auto-merge-cleanup` fuegt/enthaelt:
- `.github/workflows/auto-merge.yml`
- `.github/workflows/auto-merge-all-prs.yml`

Faktische Wirkung aus den gelesenen Workflow-Dateien:
- PR-Auto-Merge mit `pull-requests: write` und `contents: write`.
- Squash-Merge ueber GitHub CLI oder GitHub Script.
- Optionales Loeschen von Branches nach Merge.
- Scheduled Cleanup alter PR-/Branch-Referenzen.

Bewertung: nicht als normaler App-Code behandeln. Vor Uebernahme braucht es eine explizite Governance-Entscheidung, weil diese Workflows Repository-Verhalten automatisch veraendern.

## Offene Entscheidungen

1. Soll `codex/bug-task-list-2026-05-07` portiert werden oder reicht der aktuelle Branch fuer B-282?
2. Sollen stale lokale Backup-/Feature-Branches nach User-OK geloescht werden?
3. Soll `origin/main` in den aktuellen Branch uebernommen werden, obwohl es Auto-Merge aktiviert?
4. Soll `origin/workflow/auto-merge-cleanup` geschlossen/ignoriert/abgelehnt werden?
5. Soll `feat/audio-analysis-v2` in die Plan-Registry aufgenommen, archiviert oder separat neu bewertet werden?

## Verifikation

Ausgefuehrte Checks:
- `git fetch --prune origin`
- `git branch --all --verbose --no-abbrev`
- `git worktree list --porcelain`
- `git rev-list --left-right --count ...`
- `git merge-tree --write-tree ...`
- `git show --stat --name-status ...`
- `git show origin/main:.github/workflows/auto-merge.yml`
- `git show origin/workflow/auto-merge-cleanup:.github/workflows/auto-merge-all-prs.yml`

Keine App-Live-Verifikation und keine Testlaeufe pro Branch. Dieser Bericht ist ein Git-/Governance-Audit, kein Funktionsnachweis.
