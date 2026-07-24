# Implementation plan: b708-restore-db-lock (Variant A)

## Pre-checks
- [ ] Worktree `PB_studio_Rebuild_sandbox_b708-restore-db-lock` existiert, Branch `sandbox/b708-restore-db-lock`, sauber.
- [ ] conda-Python: `C:/Users/David_Lochmann/miniconda3/envs/pb-studio/python.exe`.
- [ ] Baseline in `_sandbox_meta/baseline/` erfassen: Concurrency-Repro gegen den UNVERAENDERTEN Code laufen lassen -> muss `database is locked` reproduzieren (roter Baseline-Beweis, siehe Test-Plan Schritt 0).
- [ ] User-Entscheidung zu Open-Question 2 (Lock-Modul-Verschiebung vs. Import) eingeholt.

## Steps

1. **`_timeline_write_lock` zugaenglich machen** — Ownership klaeren.
   - Default (kleinster Diff): in `services/timeline_snapshot_service.py`
     `from services.timeline_service import _timeline_write_lock` importieren.
     PRUEFEN auf Import-Zyklus: `timeline_service` importiert bereits
     `from services.timeline_snapshot_service import create_snapshot` LAZY
     (innerhalb der Funktion, Zeile ~189) — also KEIN Modul-Level-Zyklus. Import
     am Modulkopf von snapshot_service ist damit safe. Verifizieren:
     `python -c "import services.timeline_snapshot_service"` ohne ImportError.
   - Alternativ (falls User Open-Q2 so entscheidet): Lock nach
     `services/_db_locks.py` verschieben, `timeline_service` + `snapshot_service`
     beide von dort importieren. Groesserer Diff, sauberere Ownership.
   - Test: bestehende Auto-Edit-Tests muessen weiter gruen sein (Lock unveraendert benutzt).

2. **`services/timeline_snapshot_service.py::restore_snapshot`** — Write-Teil umbauen.
   - Snapshot-Read (:116-122) bleibt wie er ist (reiner Read, QueuePool ok).
   - `backup_current` (:124-128) bleibt **vor** und **ausserhalb** des Write-Locks
     (Lock-Ordnung: create_snapshot nutzt `_version_lock`; niemals gleichzeitig mit
     `_timeline_write_lock` halten -> keine Inversion gegen apply_auto_edit_segments).
   - Den `with Session(engine)` Write-Block (:130-144) ersetzen durch: Retry-Schleife
     + `with _timeline_write_lock:` + `with nullpool_session() as s:` — DELETE+INSERT
     in EINER Transaktion, Muster 1:1 wie `apply_auto_edit_segments` (:179-216).
   - Code-Sketch (<=15 Zeilen Kern):
     ```python
     import time as _time
     from sqlalchemy.exc import OperationalError
     from database.session import nullpool_session
     max_retries = 5
     for attempt in range(max_retries):
         with _timeline_write_lock:
             try:
                 with nullpool_session() as s:
                     s.query(TimelineEntry).filter_by(project_id=project_id).delete()
                     for c in clips:
                         s.add(TimelineEntry(project_id=project_id, track=c["track"],
                             media_id=c["media_id"], start_time=c["start"], end_time=c["end"],
                             lane=c["lane"], source_start=c.get("source_start", 0.0),
                             source_end=c.get("source_end"), locked=c.get("locked", False)))
                     s.commit()
                 break
             except OperationalError as e:
                 if not ("database is locked" in str(e) and attempt < max_retries - 1):
                     raise
         _time.sleep(0.5 * (attempt + 1))   # Backoff AUSSERHALB des Locks (B-683)
     ```
   - Test to add: `tests/test_services/test_b708_restore_db_lock.py::test_restore_succeeds_under_concurrent_writer`

3. **Verhalten unveraendert lassen** — kein Scope-Creep.
   - `create_snapshot`, `_version_lock`, `TimelineState`, `_apply_retention`,
     `list_snapshots` NICHT anfassen (HARTREGEL: nur B-708).
   - `_restore_snapshot` in `timeline_shell.py` NICHT anfassen (Variant A = synchron).
     `undo_stack.clear()` + `load_from_db` bleiben wie sie sind.

## Test plan

### Schritt 0 — Baseline-Repro (MUSS vor dem Fix rot sein)
- Standalone-Script `tests/repro/b708_concurrency_repro.py` (kein Mock):
  1. Temp-SQLite-DB anlegen, `Base.metadata.create_all`, ein Projekt + ein paar
     `timeline_entries` + ein `timeline_snapshot` mit Payload einfuegen.
  2. In einem Hintergrund-Thread eine **zweite** Connection (raw sqlite3 oder
     `nullpool_session`) oeffnen und `BEGIN IMMEDIATE` + einen Write auf
     `timeline_entries` absetzen, Transaktion ~3-5s **offen** halten (Write-Lock halten).
  3. Im Main-Thread `restore_snapshot(snap_id)` aufrufen.
  4. Baseline-Erwartung (UNVERAENDERTER Code): `OperationalError: database is locked`.
- Ergebnis + stderr nach `_sandbox_meta/baseline/b708_baseline.txt`.

### Schritt 1 — Unit / Concurrency (nach Fix, im Worktree)
- Gleicher Repro gegen den gepatchten Code: `restore_snapshot` blockiert am
  `_timeline_write_lock` bzw. retryt, bis der zweite Writer committet/schliesst,
  und schreibt dann erfolgreich -> KEIN `database is locked`, `timeline_entries`
  enthaelt exakt die Snapshot-Clips.
- Assertions: (a) kein Exception, (b) Row-Count == len(payload clips),
  (c) IDs neu vergeben (B-689-Verhalten unveraendert).
- Zweiter Test: `restore_snapshot` OHNE konkurrierenden Writer -> unveraendert korrekt
  (Regressionsschutz Happy-Path).
- Auto-Edit-Regression: `apply_auto_edit_segments` gemeinsam mit einem parallelen
  `restore_snapshot` -> beide serialisieren sauber, kein Deadlock (beweist Lock-Ordnung).
- Lauf: `python.exe -m pytest tests/test_services/test_b708_restore_db_lock.py -v`
  plus die bestehenden Snapshot-/Timeline-Tests (`test_timeline*`, `test_*snapshot*`).

### Schritt 2 — App-Live-Repro (durch den User, nicht per Unit verifizierbar)
- Echtes Projekt mit aktiver Timeline oeffnen (Test-Datensatz Solo_Natur + Crusty-Mix).
- Auto-Edit laufen lassen (erzeugt Snapshots), dann via Timeline-Shell-Menue einen
  aelteren Snapshot "Wiederherstellen" — idealerweise waehrend/kurz nach einem
  zweiten Auto-Edit-Apply, um den Concurrency-Fall zu treffen.
- Erwartung: Timeline zeigt den wiederhergestellten Stand, KEIN "database is locked"
  im Log, KEIN mehrsekuendiger "Keine Rueckmeldung"-Freeze (bzw. deutlich reduziert;
  vollstaendige Freeze-Freiheit erst mit Variant B — ehrlich kommunizieren).
- Log pruefen auf `[DB-Pool] Hohe Auslastung` und `DB locked bei Timeline-Write, Retry`.

## Verify-Kriterien (in verify_log.md)
- [ ] Baseline rot (Schritt 0 reproduziert `database is locked`).
- [ ] Concurrency-Test gruen (Schritt 1, alle Assertions).
- [ ] Auto-Edit-Regression gruen (kein Deadlock, Lock-Ordnung ok).
- [ ] Bestehende Snapshot-/Timeline-Tests weiter gruen.
- [ ] App-Live-Repro durch User bestaetigt (Restore erfolgreich, Freeze weg/reduziert).

## Rollback
- Worktree-Branch `sandbox/b708-restore-db-lock` verwerfen — kein Main-Impact.
- Fix ist auf 1 Funktion (+ optional 1 Lock-Import/-Modul) begrenzt; Revert = ein Diff.

## Done definition
- Alle Acceptance-Kriterien in `verify_log.md` gruen (Freeze-Kriterium ggf. als
  "reduziert" markiert, falls User Variant B nicht mitbeauftragt hat).
- Skeptic-Risiken <= P2 (insb. Lock-Ordnung P1 explizit entkraeftet: backup_current
  vollstaendig vor dem Write-Lock).
- `status: fixed` setzt der USER nach dem App-Live-Repro, nicht der Agent.
