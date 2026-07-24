# Skeptic Log: b708-restore-db-lock

Reviewer: sandbox-skeptic (read-only). Datum: 2026-07-24.

## Kommandos / Reads

1. `git diff main..sandbox/b708-restore-db-lock`
   -> nur `services/timeline_snapshot_service.py` (restore_snapshot Write-Teil)
      + neuer Test `tests/test_services/test_b708_restore_db_lock.py`.

2. Read `services/timeline_snapshot_service.py` (voll)
   - restore_snapshot: Read via Session(engine) :118-124; backup :126-130;
     neuer Write-Block :151-182 (for attempt in range(5): with _timeline_write_lock:
     try: with nullpool_session() ... commit; break; except OperationalError -> retry;
     sleep 0.5*(n+1) ausserhalb Lock).
   - create_snapshot :42-46 unter _version_lock -> Session(engine).
   - _apply_retention :49-72 Session(engine), kein Lock.

3. Read `services/timeline_service.py:1-240`
   - _timeline_write_lock = threading.Lock() :29.
   - apply_auto_edit_segments :157-216: with _timeline_write_lock -> _do_apply_segments
     + repair + create_snapshot (=> _version_lock). Ordnung WRITE->VERSION.
   - Retry-Muster identisch zum neuen restore-Code (Vorlage bestaetigt).

4. Grep nullpool_session Definition + __exit__ (`database/session.py:230-326`)
   - :248-250 cached engine, dispose_engine=False.
   - __exit__ :272-293: exc_type gesetzt -> rollback; sonst auto-commit wenn nicht
     explizit committed/rolled_back. => Retry rollt Teil-Tx sauber zurueck.
   - _TrackedSession trackt commit/rollback (M5-FIX).

5. Grep timeline_entries-Writer (services/)
   - timeline_snapshot_service.py:156/158 (neu, unter Lock).
   - timeline_service.py:349 (_do_apply_segments, unter Lock).
   - timeline_actions.py:306 add_to_timeline -> nullpool_session, KEIN Lock.
   - timeline_service.py:378 resolve_video_overlaps / :417 repair -> nullpool, Lock nur
     wenn Caller ihn haelt.
   => ungeschuetzte Writer existieren (P2).

6. busy_timeout: grep database/session.py -> busy_timeout=DB_BUSY_TIMEOUT_ANALYSIS_MS
   = 120000 ms (:130, :198). nullpool nutzt denselben Setup. => 120 s/Versuch im
   GUI-Thread moeglich (P1).

7. Restore-Caller: grep restore_snapshot
   - Prod: ui/workspaces/schnitt/timeline_shell.py:182 (Read :177-202) -> try/except
     um alles, Fehler -> status_label, KEIN Crash.
   - Tests: test_timeline_snapshot_service, test_timeline_snapshots_t23,
     test_mutating_surfaces_guards:108, test_b689 (patcht restore weg).

8. Test-Validitaet: conftest.py:116 monkeypatch database.nullpool_session -> test engine
   (global). :133-134 patcht Module mit vorhandenem nullpool_session-Attr.
   restore nutzt Lazy `from database import nullpool_session` :148 -> liest gepatchtes
   Global zur Laufzeit. test_mutating_surfaces_guards patcht nur tss.engine, funktioniert
   trotzdem, weil conftest nullpool global umbiegt. Validiert.

## Bewertung
- Lock-Ordnung: inversionsfrei (create_snapshot released _version_lock vor write_lock).
- Transaktion: atomar, Retry sauber.
- Kein P0. P1 = Freeze-Garantie fehlt (busy_timeout 120 s + Mutex-Wait, GUI synchron).
- P2 = ungehaertete Writer, stiller Backup-Verlust + luegende Statuszeile,
  create_snapshot/retention ungehaertet.

## Hinweis Vault
Skeptiker-Write-Restriktion: nur _sandbox_meta/risks.md + skeptic_log.md geschrieben.
Vault-log.md-Eintrag (HARTREGEL pro Sub-Schritt) obliegt dem orchestrierenden Agenten.

## 2026-07-24 — Variant B Threading-Audit (raw)

Commands:
- git diff main..sandbox/b708-restore-db-lock -- ui/workspaces/schnitt/timeline_shell.py
- read services/task_manager.py (start_task / _start_in_main_thread / cancel_task / _safe_cleanup)
- read services/timeline_snapshot_service.py:35-185 (restore_snapshot/create_snapshot/_version_lock)
- read services/timeline_service.py:150-245 (apply_auto_edit_segments Lock-Ordnung)
- grep create_engine/check_same_thread → database/session.py:111,188 (check_same_thread=False, busy_timeout=120s)
- grep _restore_snapshot/apply_auto_edit_segments Callsites → ui/undo_commands.py:443 (Main-Thread redo!)
- read ui/controllers/media_table.py:120-190 (Referenzmuster DBFetchWorker)
- read main.py:1035-1145 (Shutdown: _shutting_down=True, cancel_task, thread.wait 3s/Task, 10s gesamt)
- read tests: test_timeline_snapshots_t23.py:95-146, test_b689_snapshot_clears_undo_stack.py diff

Kernbefunde:
- Kein Lock-Inversion (Restore haelt _version_lock nie ueberlappend mit _timeline_write_lock).
- Worker uncancellable (kein cancel(), pollt kein interruption) + langsam (busy_timeout 120s).
- _on_restore_done except-Zweig ungeschuetzter zweiter Widget-Zugriff (status_label.setText).
- apply_auto_edit_segments auf Main-Thread (undo redo) teilt _timeline_write_lock mit BG-Restore.
- check_same_thread=False → create_snapshot(Session(engine)) aus Worker-Thread thread-safe.
