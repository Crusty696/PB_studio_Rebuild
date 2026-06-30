# B-547 Storage-Browser Delete Live — 2026-06-30

Status: **AGENT-LIVE-PASS, user-fixed marker pending**

Scope: OTK-021 90 Live-Verify / Storage-Browser Pflichtschritt 5.

## Command

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_b547_storage_browser_delete_visible.py --timeout-s 20
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_storage_browser.py tests\test_ui\test_storage_browser.py -q
git diff --check
```

## Result

- Visible verifier: Exit `0`.
- Regression tests: `10 passed in 2.34s`.
- `git diff --check`: Exit `0`.

## Evidence

- Real `StorageBrowserDialog` was shown against a temporary SQLite DB and
  temporary `storage/by_sha` root.
- The dialog listed one source: summary `1 Quellen / 4.0 KB`.
- The verifier selected the row and enabled
  `Auch Speicherdateien loeschen (gibt Plattenplatz frei)`.
- Real confirmation message:
  `Wirklich Analysen fuer 1 Quelle(n) loeschen? Inkl. physischer Dateien — Plattenplatz wird freigegeben.`
- Real success message:
  `1 Analyse-Job(s) geloescht. 1 Speicherordner geloescht, 4.0 KB freigegeben.`
- After delete:
  - table rows: `1 -> 0`
  - summary: `0 Quellen / 0 B`
  - source root exists: `true -> false`
  - `analysis_jobs`: `0`
  - `analysis_artifacts`: `0`
  - `project_sources`: `1`

Artifact:

- `tests/qa_artifacts/b547_storage_browser_delete_visible_result.json`

## Honest Limit

This proves the visible Storage-Browser delete path with a temporary real DB
and real temporary `by_sha` storage. It does not prove clean-VM install,
Project-Export/Import on another VM, Backup/Restore on VM, or DG-001 release
clearance. No `fixed` marker was set by the agent.
