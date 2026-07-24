# Verify-Log — B-708 / Variant A (Restore-Write haerten)

Durchgefuehrt vom Haupt-Agent. Stand: 2026-07-24.

## AK1 — Concurrency-Repro (deterministisch, echte File-WAL-DB)
`tests/test_services/test_b708_restore_db_lock.py::test_restore_succeeds_under_concurrent_writer`:
zweiter Thread haelt per `BEGIN IMMEDIATE` ~1.2 s den Write-Lock; parallel laeuft
`restore_snapshot`. Test-Engine mit `timeout=0` (Lock schlaegt SOFORT als
"database is locked" zu -> die Retry-Schleife, nicht ein langer busy_timeout, ist
das Behebende).
- **Baseline (unveraenderter Restore, git stash):** FAIL — `OperationalError:
  database is locked`. Rot belegt.
- **Fix:** PASS — Restore retryt (0.5+1.0+1.5 s Backoff, ausserhalb des Locks),
  bis der Halter freigibt, und schreibt erfolgreich; `timeline_entries` == 3 (Stand-A).
GREEN neu / RED alt bestaetigt.

## AK2 — Regression (Worktree)
`pytest test_b708_restore_db_lock + test_timeline_snapshots_t23 +
test_timeline_snapshot_service + test_b683_timeline_apply_retry_backoff +
test_timeline_state + tests/ui/test_b689_snapshot_clears_undo_stack` -> **22 passed**.
Bestehender Restore-Test (`test_restore_replaces_entries_and_backs_up`) unveraendert
gruen — der Fix respektiert den conftest-Monkeypatch von `database.nullpool_session`
(lazy-Import in restore_snapshot, wie timeline_service._do_apply_segments).

## AK3 — App-Live-Repro (OFFEN, durch den User)
Echtes Projekt, Auto-Edit -> Snapshot -> "Wiederherstellen" (idealerweise nahe an
einem zweiten Auto-Edit-Apply). Erwartung: Restore erfolgreich, KEIN "database is
locked" im Log, Freeze weg bzw. deutlich reduziert (vollstaendige Freeze-Freiheit
erst mit Variant B = QThread, bewusst nicht mitbeauftragt).

## AK4 — Variant B (async Worker, User-Zusatzauftrag: Freeze komplett weg)
`_restore_snapshot` (timeline_shell.py) startet den Restore jetzt via
`GlobalTaskManager.start_task` in einem Hintergrund-Worker (`_SnapshotRestoreWorker`);
`load_from_db` + `undo_stack.clear` + Status laufen im Main-Thread-Handler
`_on_restore_done` nach Worker-Erfolg. Re-Entrancy-Guard `_restore_inflight`.
Muster identisch zum produktiven media_table-DBFetchWorker.
- B-689-Fix (undo_stack.clear) in `_on_restore_done` verschoben -> B-689-Test auf den
  Handler umgestellt + neuer Async-/Re-Entrancy-Test.
- Menue-UI-Test (test_menu_populates_and_restores) auf async umgestellt (Event-Loop
  pumpen bis Worker fertig) -> gruen.
- Regression gesamt: 20 passed (b708 + b689 + snapshots_t23 + snapshot_service + retry-backoff).
- Freeze: DB-Arbeit inkl. Retry/busy_timeout laeuft nicht mehr im GUI-Thread -> P1 aus dem
  Variant-A-Audit adressiert (GUI bleibt responsiv waehrend Restore).

## Verdikt
AK1 (Lock-Fix RED->GREEN) + AK2/AK4 (Regression 20 passed) gruen; AK4 loest den P1-Freeze.
AK3 = User-App-Live-Repro. Apply-ready vorbehaltlich Skeptiker-Pass auf die Threading-Flaeche
(Variant B) + voller Suite nach Apply. status: fixed nur User.
