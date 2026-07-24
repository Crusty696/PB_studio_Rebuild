# Risks: b708-restore-db-lock (Variant A)

## Verdict
proceed-with-conditions — kein P0. Fix strukturell korrekt (Lock-Ordnung sauber,
Transaktion atomar, Tests valide). EINE ehrliche Einschraenkung (P1) muss der User
bewusst akzeptieren: Acceptance-Kriterium "kein mehrsekuendiger Freeze" ist mit
Variant A NICHT garantiert.

## P0 — blockers
- keine.

## P1 — silent regressions / criteria miss
- **Acceptance-Kriterium #3 ("Kein mehrsekuendiger Main-Thread-Freeze") wird von
  Variant A nicht garantiert** — `services/timeline_snapshot_service.py:152-182` laeuft
  weiter synchron im GUI-Thread (`ui/workspaces/schnitt/timeline_shell.py:182`, Variant A
  fasst die Shell bewusst nicht an).
  - Evidenz: `nullpool_session()` setzt `busy_timeout=120000` ms
    (`database/session.py`, `DB_BUSY_TIMEOUT_ANALYSIS_MS`, vgl. Kommentar
    `services/timeline_service.py:203-207`). Haelt ein NICHT-lock-nehmender Writer
    (s. P2) im Moment des Restore-DELETE eine SQLite-Write-Tx, wartet SQLite pro
    Versuch bis zu 120 s, BEVOR `OperationalError` fliegt. Mit 5 Versuchen + Backoff
    (0.5+1.0+1.5+2.0 = 5.0 s) ist der theoretische Worst-Case-Freeze deutlich groesser
    als das urspruengliche ~40-s-Symptom.
  - Zweiter Freeze-Vektor: `with _timeline_write_lock:` (`:153`) ist ein Python-Mutex
    ohne Timeout. Haelt ein paralleler `apply_auto_edit_segments` den Lock (grosser
    Write + `create_snapshot` + Retention), blockiert der GUI-Thread ungebremst am
    `acquire()`.
  - Ehrlich: In der Analyse als `[~]` offengelegt. Typischer Fall ist besser (kein
    QueuePool-Deadlock mehr), aber der Worst-Case-Bound STEIGT. Genau dagegen war
    Variant B gedacht.
  - Fix-Empfehlung: entweder User akzeptiert die Einschraenkung schriftlich, ODER
    Variant B (QThread) als Folgeschritt — NICHT in denselben Auftrag buendeln
    (HARTREGEL: ein Bug, ein Fix). Kein Code-Zwang jetzt.

## P2 — quality / residual
- **Ungehaertete timeline_entries-Writer, die `_timeline_write_lock` NICHT nehmen** —
  `_timeline_write_lock` serialisiert nur Writer, die ihn auch nutzen. Ungeschuetzt sind:
  - `services/actions/edit/timeline_actions.py:243` `add_to_timeline` (INSERT via
    `nullpool_session`, KEIN Lock, KEIN Retry).
  - `services/timeline_service.py:378` `resolve_video_overlaps` (Standalone-Aufruf aus
    `add_to_timeline:322-323`, KEIN Lock).
  - `services/timeline_service.py:417` `repair_timeline_integrity` (unter Lock nur, wenn
    aus `apply_auto_edit_segments:183` gerufen; Standalone-Pfade ungeschuetzt).
  Restore ueberlebt gegen diese dank Retry/busy_timeout — aber die Serialisierung ist
  NICHT total. Vorbestehend, ausserhalb B-708-Scope; nur zu benennen, nicht hier zu fixen.
- **Stiller Verlust des Undo-Backups** — `restore_snapshot:126-130`: schlaegt
  `create_snapshot` (Backup "vor Wiederherstellung") fehl, wird das nur als
  `logger.warning` geschluckt, der Restore laeuft trotzdem. Der User verliert das
  Sicherheits-Netz "Restore rueckgaengig", bekommt aber KEIN UI-Signal (die
  Erfolgs-Statuszeile `timeline_shell.py:195-198` behauptet weiter "vorheriger Stand
  wurde automatisch gesichert"). Acceptance-Kriterium #4 ("backup_current funktional")
  ist damit best-effort, nicht garantiert. Im REALEN Fall gelang das Backup — Restsymptom
  akzeptabel, aber die Statuszeile luegt im Fehlerfall.
- **`create_snapshot` + `_apply_retention` bleiben ungehaertet** —
  `timeline_snapshot_service.py:42-72` schreiben weiter ueber `Session(engine)`
  (geteilter QueuePool) unter `_version_lock`, ohne NullPool/Retry. Der Backup-Write
  kann daher weiter "database is locked" werfen (in Restore als Warnung gefangen).
  Bewusst ausserhalb Scope (ein Bug, ein Fix), aber der Fix haertet timeline_entries
  nur zur Haelfte des Snapshot-Pfads.

## P3 — notes
- Kommentarblock `:132-147` ist sehr lang (16 Zeilen Prosa vor 3 Zeilen Code).
  Inhaltlich korrekt, nur Umfang.
- `import time as _time` (Top, `:15`) dupliziert das lokale `import time as _time` in
  `apply_auto_edit_segments:168`. Kein Bug, nur zwei Konventionen fuer dasselbe.

## Checked categories
- [x] **Callsite coverage** — restore_snapshot: 1 Prod-Caller
  (`timeline_shell.py:182`, faengt alle Exceptions -> Statuszeile, kein Crash) + 5 Tests.
  Signatur unveraendert (`snapshot_id`, `backup_current`). Keine Callsite-Bruchstelle.
- [x] **Lock-Ordnung / Deadlock — KEINE Inversion.** `apply_auto_edit_segments` haelt
  `_timeline_write_lock` -> ruft `create_snapshot` -> `_version_lock` (Ordnung
  WRITE->VERSION). `restore_snapshot` beendet `create_snapshot` (nimmt+RELEAST
  `_version_lock` vollstaendig, `:126-130`) VOR `with _timeline_write_lock` (`:153`).
  Innerhalb des Write-Locks laeuft nur DELETE+INSERT, KEIN `_version_lock`. Kein Pfad
  haelt beide Locks gleichzeitig in umgekehrter Ordnung. `_apply_retention`/
  `list_snapshots` bauen keine VERSION->WRITE-Kante. Inversionsfrei bestaetigt.
- [x] **Transaktions-/Retry-Integritaet — atomar.** DELETE+INSERT in EINER
  `nullpool_session`-Tx. Bei `OperationalError` propagiert die Exception ->
  `_NullPoolSessionContext.__exit__` (`database/session.py:272-293`) sieht `exc_type` ->
  `rollback()` -> DELETE + Pending-INSERTs verworfen. Retry startet frische Session.
  Kein Teil-Write, keine Doppel-INSERTs. `_TrackedSession` verhindert Doppel-Commit.
- [x] **Test-Validitaet — Monkeypatch greift.** `conftest.py:116` patcht global
  `database.nullpool_session` -> Test-Engine; der Lazy-Import `from database import
  nullpool_session` (`:148`) liest das zur Laufzeit -> Write geht in dieselbe Test-DB
  wie der Read. `test_restore_snapshot_clears_only_snapshot_project` (patcht nur
  `tss.engine`) bleibt korrekt, weil conftest `nullpool_session` global umbiegt.
  test_b708 patcht selbst. 22 Regressionstests gruen laut Verifier.
- [x] **Behavioral drift — keine.** Gleiche Felder, gleiche DELETE+INSERT-Semantik,
  gleiche Ziel-Datei (nullpool + QueuePool zeigen auf dieselbe pb_studio.db). WAL:
  commit ist fuer den nachfolgenden `load_from_db`-Reader sichtbar. `ValueError` bei
  unbekannter snapshot_id unveraendert (`:120-121`, vor dem neuen Code).
- [x] **Migration/Compat — n/a.** Kein Schema-, Config- oder Format-Change.
- [x] **PB-Studio-Pipeline** — Pacing/Auto-Edit teilen `_timeline_write_lock`; Restore
  reiht sich additiv ein, kein Scope-Leak. Brain-V3/Schnitt-Grenzen respektiert.

## Recommendations
1. P1 explizit dem User vorlegen: Variant A reduziert den Freeze im Normalfall,
   GARANTIERT ihn aber nicht (busy_timeout 120 s/Versuch + Mutex-Wait im GUI-Thread).
   User muss "reicht mir" bestaetigen ODER Variant B als separaten Folge-Auftrag.
2. P2 Statuszeilen-Luege im Backup-Fehlerfall notieren (kein Fix-Zwang jetzt): bei
   fehlgeschlagenem Backup nicht "vorheriger Stand gesichert" melden.
3. Ungehaertete Writer (add_to_timeline / resolve_video_overlaps) als eigenen Bug
   parken — nicht in B-708 mitfixen.
4. Kein P0 -> aus Skeptiker-Sicht apply-ready UNTER Bedingung (1).

---

## Variant B — Threading (async Snapshot-Restore)

Audit-Datum 2026-07-24. Gegenstand: `_SnapshotRestoreWorker` + async `_restore_snapshot`
+ Main-Thread-Handler `_on_restore_done`/`_on_restore_failed` in
`ui/workspaces/schnitt/timeline_shell.py`. Muster 1:1 aus `ui/controllers/media_table.py`
(DBFetchWorker, produktiv).

### Verdict Variant B
proceed-with-conditions — KEIN P0, KEIN P1. Muster deckungsgleich mit produktivem
media_table-Reload. Restliche Funde sind P2 (Shutdown-Race + neuer schmaler Freeze-Vektor).

### P0 — blockers
- keine.

### P1 — silent regressions
- keine.

### P2 — quality / edge-races
- **Restore-Worker ist NICHT abbrechbar + potenziell langlaufend** —
  `timeline_shell.py:20-42` (`_SnapshotRestoreWorker`). Der Worker hat kein
  `cancel()` und pollt keine `requestInterruption()`. `restore_snapshot` blockiert
  unter DB-Contention bis zu `busy_timeout=120s` (`database/session.py:198`) × bis
  zu 5 Retries. Beim App-Schliessen kann `GlobalTaskManager.cancel_task` ihn nicht
  stoppen (`task_manager.py`: `hasattr(worker,"cancel")` → False; `thread.quit()`
  greift erst wenn `run()` zurueckkehrt). `main.py:1064-1099` wartet nur 3s/Task
  (10s gesamt) → Thread wird verwaist, App macht Hard-Exit waehrend der Worker
  noch `_timeline_write_lock` + offene Write-Txn haelt. Evidenz: identisch zum
  akzeptierten media_table-DBFetchWorker (auch uncancellable), ABER Restore ist
  deutlich langsamer als der Media-Fetch → Race-Fenster real groesser. SQLite-WAL
  rollt eine nicht-committete Txn beim Prozess-Tod zurueck → i.d.R. kein
  Datenverlust. Fix-Vorschlag: als bekannte Einschraenkung notieren (Muster-Parität
  zu media_table) oder Worker cancelbar machen — nicht in B-708 mitfixen.
- **`_on_restore_done` Except-Zweig fasst Widget ungeschuetzt an** —
  `timeline_shell.py:227-249`. Bei einer Ausnahme im try (z.B. `self.timeline`
  bereits zerstoert waehrend Close-während-Restore) ruft der `except` erneut
  `self.status_label.setText(...)` — auf ein evtl. schon zerstoertes C++-Objekt →
  `RuntimeError` UNBEHANDELT im Qt-Slot → PySide6-Prozessabbruch moeglich. Kein
  `shiboken6.isValid(self)`-Guard vor dem Handler; die on_finish/on_error-Lambdas
  halten `self` stark, aber das C++-QWidget kann beim Close bereits weg sein.
  Referenz media_table `_on_media_reload_done` fasst im Fehlerpfad KEINE Widgets
  erneut an (`media_table.py:170-184`) → Variant B ist hier fragiler. Nur relevant
  im Close-während-Restore-Race (P2). Fix: Handler mit `if not shiboken6.isValid(self): return`
  eroeffnen, ODER `status_label`-Zugriff im except in try/except kapseln.
- **Neuer Main-Thread-Freeze-Vektor via `_timeline_write_lock`** —
  `apply_auto_edit_segments` laeuft auf dem MAIN-Thread (`ui/undo_commands.py:443`,
  ApplyAutoEditCommand.redo → QUndoStack.push ist synchron). Es nimmt
  `_timeline_write_lock` (`timeline_service.py:180`). Der Restore-Worker haelt jetzt
  DENSELBEN Lock (`timeline_snapshot_service.py:153`) waehrend seines Writes. Faellt
  ein Undo/Redo-Apply zeitlich mit einem contention-verzoegerten Restore zusammen,
  blockiert der Main-Thread auf `.acquire()` bis zu busy_timeout. Vor Variant B nahm
  der Restore den Lock gar nicht → neuer (schmaler, contention-abhaengiger)
  Freeze-Pfad. Wahrscheinlichkeit niedrig (Restore-Write normal <100ms). Note.

### P3 — notes
- **T23-Menu-Test schwaecher unter async** — `test_timeline_snapshots_t23.py:138-146`
  pumpt bis 5s Wall-Clock `processEvents()` (CI-Last → Flake-Risiko) und assertet nur
  `timeline.loaded`(Stub) + Status-Text, keine DB-Inhalts-Verifikation mehr. Real-Worker
  laeuft, aber load_from_db ist gestubbt → schwaechere Aussagekraft.
- `test_restore_snapshot_runs_async_without_blocking` laesst `_restore_inflight=True`
  (FakeTM.start_task fuehrt run() nie aus) — test-lokal ok, kein Bug.
- `_restore_inflight` nie in `__init__` initialisiert → `getattr(...,False)`-Default
  (`timeline_shell.py:209`). Kein AttributeError, aber implizit. Nit.

### Geprueft — keine Funde
- [x] **Q1 Worker-Lifetime/GC** — `_restore_snapshot` ruft `start_task` vom Main-Thread
  → `_start_in_main_thread` direkt. `task.worker=worker` + `self._tasks[id]=task`
  (`task_manager.py`) halten Referenz; lokaler `worker` haelt bis Funktions-Ende.
  Kein premature GC, kein "QThread destroyed while running".
- [x] **Q2 Cross-Thread Qt** — `restore_snapshot`/`create_snapshot` reine DB-Ops
  (verifiziert `timeline_snapshot_service.py:35-185`, kein Qt/Widget/QUndoStack).
  `load_from_db` + `undo_stack.clear` NUR in `_on_restore_done` (Main-Thread, via
  `on_finish`→QueuedConnection in `task_manager._start_in_main_thread`). Sauber.
- [x] **Q3 Re-Entrancy** — `_restore_inflight` in ALLEN Reset-Pfaden zurueckgesetzt:
  Erfolg (`:231`), Fehler (`:257`), start_task-throw (`:225`). Guard + Menue-Trigger
  beide Main-Thread → kein Durchrutschen. Rest-Kante: `_shutting_down`-Pfad
  (`task_manager._start_in_main_thread`: Dummy-Return, `run()` nie aufgerufen) laesst
  inflight True — App schliesst aber ohnehin. Unkritisch.
- [x] **Q5 create_snapshot im Worker thread-safe** — Engine `check_same_thread=False`
  (`database/session.py:111,188`) → `Session(engine)` aus BG-Thread ok. `_version_lock`
  serialisiert Versionsvergabe. KEINE Lock-Inversion vs. `apply_auto_edit_segments`:
  Restore gibt `_version_lock` (backup) frei BEVOR es `_timeline_write_lock` nimmt;
  Apply nimmt write→version (genestet). Da Restore die Locks nie ueberlappend haelt →
  kein Deadlock. Verifiziert `timeline_snapshot_service.py:127-153` vs
  `timeline_service.py:180-190`.
- [x] **Q6 on_error-Signatur** — `error = Signal(str)` emittiert genau 1 str;
  `on_error=lambda msg,_v=version` matcht. `on_finish=lambda *_a,_v` vertraegt die
  0-Arg `finished`-Signal-Emission. Kein 0/2-Arg-Bruch. `_task_error_handler` nutzt
  zusaetzlich `extract_worker_error_message` robust.

### Recommendations Variant B
1. Kein P0/P1 → aus Skeptiker-Sicht apply-ready. Muster-Paritaet zu produktivem
   media_table-DBFetchWorker ist die staerkste Evidenz.
2. P2 "Except-Zweig fasst Widget ungeschuetzt an" ist der billigste Fix (1 Guard-Zeile)
   und schliesst den Close-während-Restore-Crash-Pfad — dem User als Optional vorlegen.
3. P2 Uncancellable-Worker + neuer Freeze-Vektor als bekannte Einschraenkung notieren,
   nicht in B-708 mitfixen (HARTREGEL: nur explizit Angewiesenes).
