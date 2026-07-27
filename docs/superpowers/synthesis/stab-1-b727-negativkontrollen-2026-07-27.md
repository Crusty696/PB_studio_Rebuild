# STAB-1 / B-727 Negativkontrollen — 2026-07-27

Status: `pass` für B-727-Negativkontroll-Teilgate.
STAB-1-Gesamtgate und Live-Verifikation bleiben offen.

## Root Cause

Vorheriger Guard war Parent-Prozess-lokal, band Schutz an einen einzigen
Repo-Root-Pfad und erlaubte `mode=ro`. Damit blieben Collection-Kindprozesse,
Worktree-ferne Recent-Projekt-/Brain-DBs und SQLite-URI-Pfade offen.

## Implementierung

- Test-only Guard vor `import database`.
- Dynamische Denylist aller 13 aktiven Projekt-/Vector-/Brain-DBs.
- `sqlite3.connect` und `sqlite3.dbapi2.connect` gemeinsam geschützt.
- Denylist und Aktivierung per Environment an Kinder vererbt.
- Kindprozess-Autoload über `tests/support/sitecustomize.py`.
- Jeder Originalpfad blockiert, einschließlich `mode=ro`.
- Temp-Projekt-DBs bleiben erlaubt.
- Kontrollierter Disable-Test nutzt ausschließlich synthetische Temp-DB.

## Beweise

- RED: fehlender Support-Guard.
- RED: exaktes `mode=ro` wurde nicht blockiert.
- GREEN: 15/15 B-727-Fokustests in 8,71 s.
- Geänderte Dateien: Ruff grün.
- Finales Post-Fokus-Manifest:
  `C:\Users\David_Lochmann\AppData\Local\PBStudioStability\20260727T234400+0200-stab1-b727-final-focus\manifest.json`
- 13/13 DB/WAL/SHM gegenüber Vorbaseline byte-identisch.
- 13/13 logische Hashes identisch.
- 13/13 `quick_check=ok`.

## Acht Pflichtkontrollen

1. `sqlite3.connect(real_db)` blockiert: pass.
2. `sqlite3.dbapi2.connect(real_db)` blockiert: pass.
3. Original-Connect exakt 0 Aufrufe: pass.
4. Collection-time-Zugriff: pass.
5. Kindprozess mit geerbter Testumgebung: pass.
6. APP_ROOT-/Projektwechsel-Pfad: pass.
7. Temp-Projekt-DB: pass.
8. Guard deaktiviert, synthetischer Gefährdungsbeweis: pass.

## Ehrliche Grenzen

- Kein Current-Vollsuitenlauf.
- Import-, Gesamt-Ruff-, Bandit- und Alembic-Gates noch offen.
- Keine echte App-/GUI-Verifikation.
- Status bleibt `code-fix-pending-live-verification`; kein `fixed`.

Nächste einzige Task: `STAB-1 Import-/Syntax-Smokes`.

## Adversarialer Review-Follow-up — 2026-07-28

Read-only Parallelreview fand vier HIGH-Lücken im ersten Commit `5174bf2`:

1. `file:///C:/...` aus `Path.as_uri()` umging Normalisierung.
2. Missing-DB-Pfade eines frischen Clones fehlten der Denylist.
3. Tests wählten eine existierende lokale DB per `next(...)` und wären im
   sauberen CI-Clone bei Collection mit `StopIteration` abgebrochen.
4. Zwei B-736-Defaulttests öffneten `outputs/test-tabelle` read-only direkt.

Follow-up:

- Windows-Datei-URI robust normalisiert.
- Bekannte Missing-Pfade werden für Guard-Discovery aufgenommen.
- Geschützte DB-Namen außerhalb Temp werden auch in unregistrierten Projekten
  blockiert.
- Guardtests verwenden absichtlich nicht existierenden Fresh-Clone-Pfad.
- B-736-Referenztests öffnen nur WAL-konsolidierte Temp-Kopien.

Beweise:

- neue Reviewkontrollen: 3/3 grün;
- Guard + B-734/B-735/B-736: 33/33 grün;
- Stability-Manifest-Regression: 3/3 grün;
- Ruff und `git diff --check`: grün;
- Post-Follow-up: 13/13 DB/WAL/SHM byte-/logisch identisch,
  13/13 `quick_check=ok`.

Aktualisiertes Manifest:
`C:\Users\David_Lochmann\AppData\Local\PBStudioStability\20260728T000300+0200-stab1-b727-review-followup\manifest.json`.

Nächste einzige Task bleibt: `STAB-1 Import-/Syntax-Smokes`.
