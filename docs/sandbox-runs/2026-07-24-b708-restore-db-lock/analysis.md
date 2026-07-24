# Analysis: b708-restore-db-lock

## Goal
Snapshot-Restore darf nicht mehr mit `(sqlite3.OperationalError) database is locked`
beim `INSERT INTO timeline_entries` scheitern und darf den Main-Thread nicht ~40s
einfrieren. Nach Restore muss die Timeline den wiederhergestellten Stand zeigen.

## Acceptance criteria
- [ ] Restore schreibt den Snapshot-Stand zuverlaessig in `timeline_entries` (kein `database is locked`).
- [ ] Kein harter Fehler bei gleichzeitig aktivem zweiten Timeline-Writer (serialisiert oder retryt sauber).
- [ ] Kein mehrsekuendiger Main-Thread-Freeze ("Keine Rueckmeldung") beim Restore.
- [ ] `backup_current`-Snapshot bleibt funktional (Restore rueckgaengig machbar).
- [ ] Concurrency-Repro gruen: zweiter Writer haelt Write-Lock -> Restore trotzdem erfolgreich.

## Current state

### Restore-Pfad (kaputt)
- `ui/workspaces/schnitt/timeline_shell.py::_restore_snapshot` (:177-202) ruft
  `restore_snapshot(...)` **synchron im Main-Thread (GUI)**, danach
  `self.timeline.load_from_db(project_id)` + `undo_stack.clear()`.
- `services/timeline_snapshot_service.py::restore_snapshot` (:103-148):
  1. `Session(engine)` (:116) — liest Snapshot (reiner Read).
  2. `create_snapshot(project_id, ...)` (:126) `backup_current` — eigener Writer,
     laeuft unter `_version_lock` und oeffnet INTERN mehrere Sessions:
     `TimelineState.load` (read, :47) + `save_snapshot` (read max+write+commit, :78) +
     `_apply_retention` (read+delete+commit, :49).
  3. `Session(engine)` (:130) — `DELETE FROM timeline_entries WHERE project_id`
     + INSERT-Schleife + `commit()`.
- **Alle** diese Sessions laufen ueber die **geteilte QueuePool-Engine**
  (`database.session.engine`, `Session(engine)`), also 4-5 Pool-Checkouts
  hintereinander, synchron im GUI-Thread.

### Der bereits gehaertete Vergleichspfad (funktioniert)
- `services/timeline_service.py::apply_auto_edit_segments` (:179-216) schreibt in
  **dieselbe** Tabelle `timeline_entries`, aber:
  - `with _timeline_write_lock:` (:180) — app-weiter Write-Mutex serialisiert
    gegen jeden anderen Timeline-Writer.
  - `_do_apply_segments` nutzt `nullpool_session()` (:219-225) — **frische**
    Connection pro Write, DELETE+INSERT in **einer** Transaktion, commit + close +
    dispose, **kein** Lock-Halten im Pool. Dokumentiert als D-020 / B-079.
  - Retry-Schleife auf `"database is locked"` mit Backoff **ausserhalb** des Locks
    (B-683), `max_retries`.
- Diese Haertung (M-12, B-079, B-683, D-020) ist genau die Antwort auf
  "database is locked" — und `restore_snapshot` hat sie **nie** bekommen.

### DB-Engine-Fakten (`database/session.py`)
- Haupt-Engine: `QueuePool`, `pool_size=10`, `max_overflow=30`, `busy_timeout=120000`,
  `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON` (:108-144).
- WAL: beliebig viele Reader + **genau ein** Writer. Zwei Writer gleichzeitig = `SQLITE_BUSY`.
- NullPool-Fabrik (`nullpool_session`, :230-250) existiert genau fuer Write-Pfade,
  "die 'database is locked' Fehler durch den Connection Pool bekommen" (Doc-String).

### Vorhandene Locks (getrennte Mutexe, koordinieren nicht miteinander)
- `services/timeline_service.py:29` `_timeline_write_lock` — schuetzt Timeline-Writes.
- `services/timeline_snapshot_service.py:28` `_version_lock` — schuetzt nur die Snapshot-Versionsvergabe.
- `restore_snapshot` haelt **weder** noch.

## Root-Cause (belegt am Code)

**Strukturelle Ursache — belegt:** `restore_snapshot` ist der einzige verbliebene
Timeline-`timeline_entries`-Writer, der die etablierte Haertung umgeht:

1. **Geteilter QueuePool statt NullPool.** `restore_snapshot` schreibt via
   `Session(engine)` (:130). Der Rest des Write-Pfads wurde bewusst auf NullPool
   umgestellt (D-020, B-079), weil pooled Connections mit offener/RESERVED-Transaktion
   im Pool zurueckbleiben und einen zweiten Writer blockieren. Genau dieses Muster.
2. **Keine Serialisierung gegen `_timeline_write_lock`.** Jeder andere Timeline-Writer
   (ein noch nicht ganz fertiger Auto-Edit-Apply, dessen Auto-`create_snapshot`, ein
   Retention-`DELETE`) kann parallel eine Write-Transaktion auf `timeline_entries` /
   `timeline_snapshots` halten. SQLite erlaubt nur **einen** Writer -> `SQLITE_BUSY`.
3. **Kein Retry.** `apply_auto_edit_segments` faengt `"database is locked"` und retryt.
   `restore_snapshot` re-raist beim ersten `SQLITE_BUSY` -> harter Fehler, Feature unbrauchbar.
4. **Main-Thread synchron.** Weil `_restore_snapshot` blockierend laeuft, wartet der
   `busy_timeout` (bzw. der Lock-Konflikt) **im GUI-Thread** -> ~40s "Keine Rueckmeldung".

**Warum Fehler nach ~40s statt 120s busy_timeout:** `busy_timeout` wartet nur bei
reinem Lock-Warten. Bei einem **Deadlock/Upgrade-Konflikt** (zwei Pool-Connections,
eine haelt eine offene Read-/RESERVED-Transaktion, der Writer will EXCLUSIVE bzw. ein
`SQLITE_BUSY_SNAPSHOT` beim read->write-Upgrade in `save_snapshot`/`TimelineState`)
gibt SQLite **sofort** `SQLITE_BUSY` zurueck statt den Timeout abzuwarten. Der
Multi-Session-QueuePool-Split von `restore_snapshot` (5 Checkouts, `create_snapshot`
mit read->write-Upgrade in derselben Connection) ist genau der Naehrboden dafuer.

**Ehrlichkeits-Hinweis:** WELCHE exakte Connection den Lock im Live-Repro hielt, ist
aus reinem Code-Lesen **nicht** 100 % eindeutig bestimmbar — das braeuchte einen
Laufzeit-Trace (py-spy / SQLite-Lock-Logging). Die strukturelle Ursache (QueuePool +
fehlende Serialisierung + kein Retry + Main-Thread) ist dagegen eindeutig belegt und
deckt sich mit der bereits dokumentierten Historie desselben Fehlerbilds im
Auto-Edit-Pfad. Der Concurrency-Repro (siehe plan.md) macht den Lock-Halter
deterministisch reproduzierbar und beweist Fix-Wirkung.

## Variants

### Variant A — Restore an den gehaerteten Auto-Edit-Write-Pfad angleichen
**Approach:** `restore_snapshot` so umbauen, dass der eigentliche Write (DELETE+INSERT)
in **einer** `nullpool_session()`-Transaktion laeuft, serialisiert unter dem
**vorhandenen** `_timeline_write_lock`, mit derselben Retry-auf-"database is locked"-
Schleife wie `apply_auto_edit_segments`. `backup_current` (`create_snapshot`) laeuft
**vor** und **ausserhalb** des `_timeline_write_lock` (Lock-Ordnung, s.u.). Der reine
Snapshot-Read (:116) darf QueuePool bleiben (Read blockiert Writer in WAL nicht).
- **Files touched:** `services/timeline_snapshot_service.py` (restore_snapshot);
  `_timeline_write_lock` aus `services/timeline_service.py` importieren ODER in ein
  neutrales Modul (z.B. `database/session.py` oder neues `services/_db_locks.py`)
  ziehen, um Import-Zyklus/Ownership sauber zu halten.
- **New deps:** keine (nutzt vorhandene Bausteine).
- **Effort:** S-M.
- **Risk:** P1 Lock-Ordnung: Auto-Edit haelt `_timeline_write_lock` -> ruft
  `create_snapshot` -> will `_version_lock` (Ordnung WRITE->VERSION). Restore MUSS
  daher `create_snapshot` (VERSION) **vollstaendig vor** dem Nehmen von
  `_timeline_write_lock` abschliessen, damit die beiden Locks nie gleichzeitig
  gehalten werden -> keine Ordnungs-Inversion, kein Deadlock. P2: Import des Locks.
- **Reversibility:** leicht (eine Funktion, ein Modul).

### Variant B — Restore in Worker-Thread + App-weite Write-Serialisierung
**Approach:** Wie A (NullPool + `_timeline_write_lock` + Retry), zusaetzlich
`_restore_snapshot` in der Shell in einen QThread verlagern; `load_from_db` +
`undo_stack.clear()` erst im `finished`-Slot im Main-Thread. Eliminiert den Freeze
vollstaendig.
- **Files touched:** `services/timeline_snapshot_service.py` **und**
  `ui/workspaces/schnitt/timeline_shell.py` (QThread-Worker, Signal-Verdrahtung,
  Fehler-/Abbruch-Pfad).
- **New deps:** keine.
- **Effort:** M-L.
- **Risk:** P1 Qt-Threading: Worker-Lifecycle, Signal-Reentrancy gegen den
  bestehenden `_cancel_pending_db_load`-Mechanismus in `load_from_db`, Fehler-Routing
  in den GUI-Thread. Mehr bewegliche Teile = groesseres Regressionsrisiko in einem
  UI-Pfad, den B-283/B-598/M3 schon empfindlich gemacht haben.
- **Reversibility:** mittel.

### Variant C — Minimal: nur QueuePool->NullPool + Retry, ohne Lock-Teilen
**Approach:** In `restore_snapshot` `Session(engine)` -> `nullpool_session()`,
DELETE+INSERT in eine Transaktion, Retry-Schleife auf "database is locked". **Kein**
`_timeline_write_lock`.
- **Files touched:** `services/timeline_snapshot_service.py` nur.
- **New deps:** keine.
- **Effort:** S.
- **Risk:** P1 — ohne `_timeline_write_lock` bleibt das Write-Write-Konfliktfenster
  gegen echte parallele Timeline-Writer offen; Retry+busy_timeout **mildern**, aber
  **garantieren** die Serialisierung nicht (genau der Deadlock-/BUSY_SNAPSHOT-Fall,
  der busy_timeout umgeht, kann bleiben). Schwaecher als A bei praktisch gleichem Aufwand.
- **Reversibility:** leicht.

## Recommendation

**Variant A.** Sie spiegelt exakt den bereits im Live-Betrieb bewaehrten,
mehrfach gehaerteten Auto-Edit-Write-Pfad (NullPool + `_timeline_write_lock` + Retry,
alles in einer Transaktion) und erfindet nichts Neues. Sie behebt die eigentliche
Ursache (Write-Write-Lock) **sicher** und reduziert den Freeze deutlich (kurzes
effektives Lock-Fenster, Backoff ausserhalb des Locks, kein QueuePool-Warten auf
verwaiste Connections).

Warum nicht C: gleicher Aufwand, aber ohne den Write-Mutex bleibt genau das
Konfliktfenster offen, das den Bug ausloest. Warum nicht B als Erststep: B loest
primaer das **Symptom** Freeze und bringt echtes Qt-Threading-Regressionsrisiko in
einen bereits fragilen UI-Pfad. B ist der **richtige Folgeschritt**, falls nach A ein
Restrest-Freeze bei sehr grossen Timelines stoert — additiv auf A aufsetzbar. A und B
NICHT buendeln (HARTREGEL: nur explizit Angewiesenes; ein Bug, ein Fix).

**Ehrliche Einschraenkung:** A garantiert "kein Lock" gegen alle **prozess-internen**
Timeline-Writer (alle laufen jetzt unter demselben `_timeline_write_lock`). Ein
komplett-freeze-freier Restore ist erst mit B garantiert; A reduziert den Freeze,
eliminiert das busy_timeout-Warten im Main-Thread aber nicht in jedem Fall zu 100 %.

### Acceptance-Criteria-Abdeckung (Variant A)
- [x] Restore schreibt zuverlaessig -> NullPool + Retry + Serialisierung.
- [x] Kein harter Fehler bei zweitem Writer -> `_timeline_write_lock` serialisiert; Retry als Netz.
- [~] Kein Freeze -> deutlich reduziert; vollstaendige Elimination erst mit B (ehrlich markiert).
- [x] `backup_current` funktional -> unveraendert, nur vor den Write-Lock gezogen.
- [x] Concurrency-Repro gruen -> siehe plan.md Test-Plan.

## Cross-team impact
- **Platform/DB:** Kern der Aenderung. Angleich an D-020/B-079-NullPool-Doktrin. Ein
  gemeinsam genutzter `_timeline_write_lock` (ggf. verschoben) betrifft auch
  `apply_auto_edit_segments` — bei Modul-Verschiebung des Locks Import in
  `timeline_service.py` mitziehen (sonst zwei getrennte Locks = Bug).
- **UI/Schnitt:** Variant A laesst `_restore_snapshot` synchron; nur Verhalten
  robuster. Variant B wuerde den QThread-Pfad in `timeline_shell` + `load_from_db`
  beruehren (B-283/B-598-Territorium).
- **ML/GPU:** nicht betroffen.
- **Audio/Video/Pacing:** nicht direkt; `apply_auto_edit_segments` (Pacing/Auto-Edit)
  teilt den Lock — Regressionstest des Auto-Edit-Applys ist Pflicht.

## Open questions for user
1. Freeze: reicht "deutlich reduziert" (Variant A) fuer jetzt, oder soll der Restore
   sofort komplett freeze-frei sein (dann A **plus** B in EINEM Auftrag — bitte
   explizit anweisen, sonst bleibt es bei A)?
2. `_timeline_write_lock` teilen: OK, den Lock nach `services/_db_locks.py` (oder
   `database/session.py`) zu verschieben und `timeline_service` darauf umzustellen,
   oder soll `restore_snapshot` den Lock **aus** `timeline_service` importieren
   (kleinerer Diff, aber Ownership bleibt bei timeline_service)?
