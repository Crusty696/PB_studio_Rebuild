# Full Project Conflict Quality Audit - Inventory 2026-06-07

plan_id: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07
task: Task 1 Inventory And Exclusion Map
status: static-complete
mode: audit-plan
created: 2026-06-07

## Task Quote

```text
Build complete repository file inventory, classify every file as included, excluded, or targeted-only, and write coverage evidence before deeper review.
```

## Evidence Commands

```powershell
git status --short --branch
git ls-files
git status --short --untracked-files=all
git status --ignored --short --untracked-files=all
git ls-files | Measure-Object
```

Observed:

- Branch: `codex/PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31`, ahead 1 after governance commit.
- `git status --short --untracked-files=all`: no untracked non-ignored files before inventory artifacts.
- `git ls-files`: 1187 tracked files.
- `git status --ignored --short --untracked-files=all`: 1451 ignored paths.

## Inventory Artifacts

- `docs/superpowers/synthesis/full-project-conflict-quality-audit-inventory-files-2026-06-07.tsv`
- `docs/superpowers/synthesis/full-project-conflict-quality-audit-ignored-files-2026-06-07.tsv`

The tracked-file TSV classifies each tracked file as `included` or `targeted-only`.
The ignored-file TSV classifies ignored paths as `excluded-ignored`.

## Tracked Coverage

| Class | Count | Meaning |
|---|---:|---|
| included | 1163 | Default audit surface: source, tests, docs, scripts, config, CI. |
| targeted-only | 24 | Binary/data/report/vendor/storage/asset paths; inspect only when direct finding evidence needs them. |
| total tracked | 1187 | Count from `git ls-files`. |

## Top Tracked Directories

| Directory | Count |
|---|---:|
| `tests` | 476 |
| `docs` | 253 |
| `services` | 185 |
| `ui` | 94 |
| `scripts` | 39 |
| `<root>` | 30 |
| `tools` | 22 |
| `database` | 15 |
| `workers` | 13 |
| `.github` | 9 |

## Main Extension Classes

| Extension | Count |
|---|---:|
| `.py` | 832 |
| `.md` | 264 |
| `.json` | 18 |
| `.sql` | 8 |
| `.yaml` | 8 |
| `.yml` | 8 |
| `.bat` | 7 |
| `.ps1` | 6 |
| `.txt` | 5 |
| `.png` | 4 |

## Targeted-Only Tracked Paths

Direct binary/data/report evidence:

- `config/mood_anchors.npz`
- `pb_studio.db.b319_backup_20260514_200816`
- `resources/installer_header.bmp`
- `resources/installer_welcome.bmp`
- `resources/pb_studio.ico`
- `resources/pb_studio.png`
- `resources/pb_studio_icon.png`
- `test_reports/save_click_after_b459_2026-06-02.png`
- `test_reports/tools_menu_2026-06-02.png`

Area-level targeted-only groups:

- `installer/`
- `resources/`
- `storage/`
- `test_reports/`
- `vendor/`

These paths are not ignored. They remain audit-visible, but not manually read line-by-line unless directly relevant.

## Ignored / Excluded Coverage

Ignored path count: 1451.

Top ignored groups:

| Group | Count | Exclusion reason |
|---|---:|---|
| `tests` | 524 | ignored generated test artifacts/cache paths |
| `services` | 349 | ignored generated/runtime artifacts under service paths |
| `ui` | 187 | ignored generated/runtime artifacts under UI paths |
| `.ruff_cache` | 114 | tool cache |
| `.agents` | 72 | local agent skill/tooling cache |
| `database` | 28 | ignored generated/runtime DB artifacts |
| `workers` | 26 | ignored generated/runtime artifacts |
| `.claude` | 21 | local agent memory/logs/settings |
| `storage` | 20 | runtime/generated storage |
| `.superpowers` | 15 | local skill/tooling state |
| `logs` | 13 | runtime logs |
| `outputs` | 6 | generated outputs |
| `__pycache__` | 6 | Python bytecode cache |
| `.pytest_cache` | 5 | pytest cache |
| `<root-file>` | 4 | ignored root-local files including `.env`/runtime DB files |

Ignored paths are excluded from manual every-file reading in this audit unless targeted evidence requires them. `.env` is ignored and not read.

## Not Checked Yet

Task 1 did not inspect source behavior, test behavior, imports, call sites, UI wiring, runtime logs, or live workflows. Those belong to Task 2 and Task 3.

## Verification Status

Static inventory complete. No app code changed. No live verification performed. No finding marked fixed.
