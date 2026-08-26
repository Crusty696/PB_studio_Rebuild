# PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12 (CRF)

> **⛔ SUPERSEDED 2026-07-16 — PLAN GESCHLOSSEN.** Alle offenen Tasks wurden in
> `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16` konsolidiert (Decision D-071, Registry-Status
> `superseded`). Dieser Plan wird NICHT mehr als aktiver Plan genutzt; der Task-Text bleibt
> nur als Historie. Aktuelle offene Arbeit:
> `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

plan_id: PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12
status: approved-for-implementation (User-Auftrag 2026-06-12: "Erstelle Arbeitsplan ... und übergib es dem passenden Agenten um den Plan auszuführen")
source: test_reports/consulting-team-review-2026-06-12.md (Consulting-Team-Review, 7 Agenten, statisch)
decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-062-consulting-review-fixplan.md
vault_mirror: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-consulting-review-fixplan-2026-06-12.md
updated: 2026-06-12

## Geltungsregeln (nicht verhandelbar, aus AGENTS.md)

1. **Status-Cap:** Kein Agent setzt `fixed`. Maximum = `code-fix-pending-live-verification`. `fixed` setzt nur der User nach echtem Live-Workflow.
2. **Sequenziell:** Ein Task zur Zeit, ein Agent zur Zeit im Worktree. Kein Parallel-Edit.
3. **Root cause vor Quick-Fix.** Kein defensives try/except als "Fix".
4. **Pro Task:** Code-Edit → Import-/Syntax-Check → Unit-Test schreiben+laufen lassen → Vault-Bugfile → log.md-Eintrag → Commit `fix(B-XXX): <kurz>` mit Body `(unverified — pending user test)`.
5. **Nur die hier beschriebenen Änderungen.** Keine While-I'm-here-Fixes. Neue Funde → neues Bugfile, nicht mitfixen.
6. **Tests laufen mit dem in CRF-002 ermittelten kanonischen Interpreter** (py310-Env), niemals mit System-Python.
7. **One-way-door-Tasks (Wave 4 D-Tasks) werden NICHT von Agenten ausgeführt** — nur Entscheidungsvorlage für User.

## Bug-ID-Zuordnung (Vault-Höchststand vor Plan: B-497)

| Task | Bug-ID | Finding | Severity |
|---|---|---|---|
| CRF-001 | B-498 | C-1 Kein Auto-Backup Haupt-DB | 🔴 |
| CRF-002 | B-499 | C-2 Runtime-/Dependency-Drift | 🔴 |
| CRF-003 | B-500 | C-3 clear_finished deleteLater auf laufende Threads | 🔴 |
| CRF-004 | B-501 | C-4 Waveform Full-Load + nutzloses beat_track | 🔴 |
| CRF-005 | B-490/B-491 | H-4 Engine-Swap mid-run + Assign-Mode-Restloch | 🟠 |
| CRF-006 | B-504 | H-5 Concat UTF-8 + duration/outpoint | 🟠 |
| CRF-007 | B-505 | H-6 Proxy-NVENC ohne Serializer/Fallback | 🟠 |
| CRF-008 | B-506 | H-7 600s-Timeout vs lange Quellen | 🟠 |
| CRF-009 | B-507 | H-8 Totes Cancel-Flag _gpu_cancel_requested | 🟠 |
| CRF-010 | B-508 | H-9 Unbegrenzte Thumbnail-Threads | 🟠 |
| CRF-011 | B-509 | H-10 Alembic-Drift | 🟠 |
| CRF-012 | B-502 | H-2 GPU-Lock-Schisma Modell-Load | 🟠 |
| CRF-013 | B-503 | H-3 GpuSerializer non-reentrant + Async blockiert | 🟠 |
| CRF-014 | B-510 | H-11 Demucs-Input + SubtrackDetector Skalierung | 🟠 |
| CRF-015 | B-511 | M-1 fp16-NaN-Runtime-Check | 🟡 |
| CRF-016 | B-512 | M-2 sleep+DB im GUI-Thread (Undo) | 🟡 |
| CRF-017 | B-513 | M-3 run_worker Teardown | 🟡 |
| CRF-018 | B-514 | M-4 Fehlende Indizes | 🟡 |
| CRF-019 | B-515 | M-5 gitignore-Lücken + getrackte DB-Backups | 🟡 |
| CRF-020 | B-516 | M-6 F821/Lint + tests/test_pacing.py | 🟡 |
| CRF-021 | B-517 | M-7 Batch-Convert copy/-vf/-preset/NVENC-Mapping | 🟡 |
| CRF-022 | B-518 | M-8 services→ui-Kante pacing_strategist | 🟡 |
| CRF-023 | B-519 | M-9 CLAP-Lease ohne Cancel + librosa-Fallback-Cap | 🟡 |
| CRF-024 | B-520 | L CREATE_NO_WINDOW + nackte threading.Thread | 🟢 |
| CRF-D1 | — | H-1 Brain v1/v2/v3-Deprecation | USER-Entscheidung |
| CRF-D2 | — | M-10 Vault-Sync-Strategie | USER-Entscheidung |
| CRF-D3 | — | C-2-Folge: cu121-Migration ja/nein | USER-Entscheidung |

---

## WAVE 1 — Critical (Reihenfolge zwingend: CRF-002 zuerst, liefert Interpreter für alle Tests)

### CRF-002 / B-499 — Runtime-Diagnose + Interpreter-Hard-Check (Diagnose + kleiner Code-Fix)

**Ziel:** Eindeutig klären welche Umgebung produktiv ist; verhindern dass App-Code je wieder unter falschem Interpreter läuft.

Schritte:
1. Diagnose (read-only, via Shell): `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv` (voller Pfad `C:\Windows\System32\nvidia-smi.exe` falls PATH leer). Ergebnis dokumentieren: Treiber 461.40 oder 546.33 oder anderes.
2. Kanonischen Interpreter finden: Conda-Envs (`conda env list`), `.venv`-Ordner, Start-Skripte (`setup_pb_studio.bat`, `tools/`, `bin/`) lesen. Kriterium: Python 3.10 + torch 1.12.1+cu113 importierbar (`python -c "import torch; print(torch.__version__, torch.version.cuda)"`). Pfad in Bugfile + Vault-Mirror notieren.
3. Quelle der cpython-313-Pycs identifizieren: `python3.13`-Installationen suchen (`py -0p`), prüfen welche Tools (MCP-Server, Skripte) damit laufen. NICHT löschen, nur dokumentieren.
4. Code-Fix in `services/startup_checks.py`: neue Check-Funktion `check_python_version()` — bei `sys.version_info[:2] != (3, 10)` harte Fehlermeldung im Startup-Dialog (bestehende Check-Infrastruktur der Datei nutzen, gleiches Pattern wie vorhandene Checks). Kein Auto-Exit ohne Dialog.
5. `requirements.txt` Kopfkommentar ergänzen (nur Kommentar, keine Pins ändern): "NICHT INSTALLIEREN — Legacy/Future. Kanonisch: requirements-py310-cu113.txt". Löschen/Archivieren der Datei = CRF-D3/User.
6. Unit-Test: `tests/test_services/test_startup_python_version.py` — monkeypatch `sys.version_info`, Check liefert fail/pass korrekt.

Verifikation: Import-Check + neuer Test grün + bestehende startup_checks-Tests grün. Status: `code-fix-pending-live-verification` (Live = App-Start zeigt keinen False-Positive).
Commit: `fix(B-499): python version hard check + runtime diagnosis`

### CRF-001 / B-498 — Automatisches DB-Backup verdrahten + WAL-sicher kopieren

**Dateien:** `services/backup_service.py`, `main.py`, `database/migrations.py`, `services/project_manager.py` (nur als Referenz lesen, Zeilen 420-434, B-137-Pattern).

Schritte:
1. `backup_service.py:77` — `shutil.copy2`-Hot-Copy ersetzen durch `sqlite3.Connection.backup()`-API (Pattern aus `project_manager.py:420-434` übernehmen: source-Connection read-only öffnen, `conn.backup(dest_conn)`, beide schließen, try/finally). Docstring Zeile 10-11 ("WAL allows hot-copy safely") korrigieren.
2. `backup_if_stale(reason="daily")` beim App-Start verdrahten: in `main.py` nach erfolgreichem `init_db()`/Migrations-Lauf, VOR Worker-Starts. Fehler im Backup dürfen den Start NICHT blockieren (log.error + weiter), aber müssen sichtbar geloggt werden.
3. `database/migrations.py:347` — vor `alembic upgrade head` ein Backup über denselben BackupService-Pfad ziehen (reason="pre-migration"). Bestehendes FK-Migrations-Backup (Z.300-307) nicht anfassen.
4. Retention prüfen: vorhandene Stale-/Rotation-Logik in backup_service beibehalten; falls keine Rotation existiert: max. 7 daily-Backups, älteste löschen (klein halten).
5. Tests: `tests/memory/test_backup_service.py` erweitern — (a) Backup einer DB mit offenem WAL enthält letzten Commit (Schreiben → Backup → Backup öffnen → Daten da), (b) pre-migration-reason erzeugt Datei, (c) Backup-Fehler crasht Aufrufer nicht.

Verifikation: pytest tests/memory/test_backup_service.py grün; Import-Check main.py. Status-Cap. Live-Test-Anweisung an User: App starten → Backup-Datei mit heutigem Datum unter Backup-Pfad prüfen.
Commit: `fix(B-498): wire automatic db backup, WAL-safe copy, pre-migration backup`

### CRF-003 / B-500 — clear_finished() darf laufende Threads nicht zerstören

**Datei:** `services/task_manager.py:497-523` (+ `_safe_cleanup`-Pfad lesen, Z.~529ff, und `cancel_task` Z.447-485).

Schritte:
1. In `clear_finished()` innerhalb des Locks pro Kandidat prüfen: `task.thread is not None and shiboken6.isValid(task.thread) and task.thread.isRunning()` → Task ÜBERSPRINGEN (nicht poppen, kein deleteLater). Er bleibt in `_tasks`, bis `thread.finished` → `_on_thread_done`/`_safe_cleanup` ihn regulär abräumt.
2. Sicherstellen dass übersprungene cancelled-Tasks später wirklich abgeräumt werden: prüfen dass `_on_thread_done` auch für Status "cancelled" den Task entfernt/cleanup triggert. Falls nicht: dort nachziehen (gleicher Bug, gleiche Wurzel — gehört in diesen Fix).
3. Kommentar im Code: Verweis auf B-500 + warum isRunning-Check zwingend (Qt-FATAL bei Destroy-while-running).
4. Tests: `tests/test_services/test_task_manager_clear_finished.py` — (a) Task mit gemocktem Thread `isRunning()=True`, Status "cancelled" → bleibt nach clear_finished() in get_all_tasks(), kein deleteLater-Call (Mock assert); (b) Thread `isRunning()=False` → wird entfernt; (c) Regression: status "running" bleibt unberührt.

Verifikation: neue + bestehende task_manager-Tests grün. Status-Cap. Live-Anweisung an User: langen Task starten → abbrechen → sofort "Fertige löschen" klicken → App darf nicht crashen; Task verschwindet erst wenn Worker wirklich fertig.
Commit: `fix(B-500): skip running threads in clear_finished, prevent QThread destroy crash`

### CRF-004 / B-501 — Waveform-Analyse: Chunked STFT + totes beat_track entfernen

**Datei:** `services/ai_audio_service.py` FrequencyAnalyzer (`analyze` ~Z.1030-1140, `analyze_and_store` Z.1142-1192). Referenz-Pattern: `services/beat_analysis_service.py:384` (`_analyze_chunked`), `services/audio_constants.py` (CHUNK_DURATION_SEC, MAX_DURATION_*).

Schritte:
1. `analyze()` umbauen auf Block-Verarbeitung: Dauer vorab via `librosa.get_duration(path=file_path)`. Bei Dauer > 600 s: Audio in Blöcken laden (`librosa.load(file_path, sr=self.SR, mono=True, offset=block_start, duration=BLOCK_SEC)`, BLOCK_SEC=600), pro Block STFT → Band-Energien (low/mid/high, bestehende Masken-Logik) → an Ergebnis-Arrays anhängen, Block-Speicher freigeben. Bei Dauer ≤ 600 s: bestehender Pfad unverändert.
2. Normalisierung der Bänder NACH der Block-Schleife global durchführen (sonst normalisiert jeder Block gegen eigenes Maximum → sichtbare Sprünge an Blockgrenzen — das ist die fachliche Falle dieses Umbaus, im Test abdecken).
3. Downsampling auf `num_samples` (bestehende Ziel-Auflösung ~4000) nach Zusammenbau.
4. `librosa.beat.beat_track`-Aufruf (Z.~1096) komplett entfernen. `bpm`-Feld: nur falls `track.bpm is None` nötig → stattdessen vorhandenen BPM aus DB/BeatAnalysisService übernehmen; Rückgabefeld `beat_positions` aus Signatur/Aufrufern entfernen oder leer liefern — Aufrufer vorher grep-en (`beat_positions`) und konsistent anpassen. Docstring von `analyze_and_store` korrigieren (kein Beatgrid-Write).
5. MP3-Fallback-Risiko (audioread O(n²) bei offset-Loads) dokumentieren: im Bugfile als bekannte Einschränkung notieren, NICHT in diesem Task lösen.
6. Tests: `tests/test_services/test_frequency_analyzer_chunked.py` — (a) synthetisches 2-Block-Signal (z.B. 1250 s Sinus via numpy direkt an interne Block-Funktion, Datei-IO mocken): Ergebnis-Länge korrekt, keine Diskontinuität an Blockgrenze (Differenz benachbarter Werte < Schwellwert bei konstantem Signal), (b) kurzes Signal nutzt Single-Pass, (c) kein beat_track-Aufruf mehr (Mock assert).

Verifikation: neue Tests + bestehende ai_audio_service-Tests grün. Status-Cap. Live-Anweisung: 60-min+-Mix importieren → Waveform erscheint, RAM-Peak im Task-Manager < 1 GB für diesen Schritt.
Commit: `fix(B-501): chunked waveform STFT, remove dead beat_track`

## WAVE 2 — High (Gruppen, sequenziell: erst FFmpeg, dann Qt, dann DB)

### CRF-006 / B-504 — Export-Concat: UTF-8 + outpoint

`services/export_service.py`: (1) Z.746-748 `NamedTemporaryFile(..., encoding="utf-8")` ergänzen (Vergleich Z.940-943). (2) Z.736-743/756-761: Branch "konform ohne Offset" — wenn Segment-Dauer < Clip-Dauer: `inpoint 0` + `outpoint <dauer>` schreiben statt nur `duration`. ffprobe-Clipdauer ist im Umfeld bereits verfügbar; sonst einmal proben. (3) `_needs_preprocessing` (Z.~76-97): zusätzlich `avg_frame_rate != r_frame_rate` (VFR-Indiz) und abweichendes `pix_fmt` als "needs preprocessing" werten. Tests: Concat-Listen-Generierung unit-testen (Tempfile lesen: UTF-8-Umlautpfad intakt, outpoint vorhanden). Commit: `fix(B-504): concat list utf-8 + outpoint trim + vfr/pixfmt probe`

### CRF-007 / B-505 — Proxy-Encodes unter GpuSerializer + Fallback

(1) `services/video_service.py:232-253` `create_proxy`: NVENC-Aufruf in `get_default_serializer().acquire(...)`-Kontext (Pattern `export_service.py:1258-1261`); bei FFmpeg-Fehler mit NVENC-Signatur (`OpenEncodeSessionEx`, `Cannot load nvcuda`) einmaliger Retry mit `libx264 -preset veryfast`. (2) `services/video_pipeline/primitives/proxy_generator.py:71-88` + `stages/proxy_gen_stage.py:47`: dito Serializer; `TimeoutExpired` im `auto`-Pfad fangen → CPU-Fallback statt Abbruch. Tests: subprocess mocken — Serializer-acquire wird betreten (Mock), NVENC-Fail → libx264-Kommando abgesetzt. Commit: `fix(B-505): proxy encodes under gpu serializer with cpu fallback`

### CRF-008 / B-506 — Dynamische FFmpeg-Timeouts

(1) `services/timeout_constants.py`: Helper `ffmpeg_timeout_for(duration_sec, min_sec=600, factor=3.0)`. (2) `workers/import_export.py:484` und `:572`: Dauer via vorhandener ffprobe-Helper ermitteln, `timeout=ffmpeg_timeout_for(dauer)`; wenn Dauer unbekannt → bisheriger Default. Vorbild `export_service.py:815`. Tests: Helper-Mathematik + Aufruf-Verdrahtung (Mock). Commit: `fix(B-506): duration-based ffmpeg timeouts in batch convert/proxy`

### CRF-009 / B-507 — Cancel-Pfad real machen

`services/task_manager.py:481-482`: totes `_gpu_cancel_requested`-Konstrukt entfernen. Stattdessen: in `cancel_task()` zusätzlich `worker.cancel()` aufrufen falls vorhanden (BaseWorker-API `workers/base.py:39-58`). Dann Inventur: grep alle Worker-`run()`-Loops mit GPU-Nutzung (workers/video.py, audio-Worker, brain_v3-Stages) — prüfen dass sie `should_stop()`/`is_cancelled` periodisch abfragen UND GPU-Locks im `finally` freigeben. Wo der Check fehlt und trivial einfügbar ist (Schleifenkopf): einfügen; wo strukturell größer: nur im Bugfile als Folge-Finding dokumentieren. Tests: cancel_task ruft worker.cancel (Mock); ein Beispiel-Worker bricht Schleife ab. Commit: `fix(B-507): remove dead gpu cancel flag, wire worker.cancel into cancel_task`

### CRF-010 / B-508 — Thumbnail-Generierung poolen

`ui/widgets/media_grid.py`: Thumbnail-Loads (Z.674-701) von Thread-pro-Card auf geteilten `QThreadPool` umstellen: modulweiter Pool `setMaxThreadCount(4)`, `QRunnable` der `subprocess` + Signal-Emission via QObject-Holder kapselt (PySide6: Signals brauchen QObject — Holder-Pattern). Cancel beim Widget-Destroy: Runnable prüft `shiboken6.isValid(card)` vor Emit. Tests: UI-Test mit 20 Dummy-Cards → max 4 gleichzeitige "Starts" (instrumentierter Fake-Runner). Commit: `fix(B-508): bounded thumbnail thread pool`

### CRF-005 / B-490+B-491-Followup — Pipeline-Projekt-Token + Assign-Degraded-Fallback

(1) B-490: `services/video_analysis_service.py` — beim Pipeline-Start Projekt-Identität festhalten (z.B. `database/session.py` aktuelle Engine-URL/Projekt-ID); `store_scenes_in_db` (Z.952-964) und der Caller (Z.1222-1226, 1405-1409): bei Projekt-Mismatch oder Skip → `mark_error("scene_db_storage", reason)` statt still skip + `mark_done`. Rückgabewert `stored: bool` einführen. (2) `database/session.py:339-342`: `set_project()` — wenn TaskManager laufende Tasks hat: Exception/Abbruch mit klarer Meldung statt Log-Warnung (Aufrufer in UI: Dialog "Projektwechsel erst nach Abschluss/Abbruch laufender Tasks"). UI-Aufrufer grep-en und Meldung anzeigen. (3) B-491: `workers/structure_enrichment.py:499-525` Assign-Modus — vor `load_reducer`: existiert Reducer-Datei? Buckets in DB als degraded markiert? → Single-Bucket-Fallback wie Fit-Pfad (Z.473-478), kein Crash. `style_bucket_clusterer.py`: `load_reducer` darf FileNotFound werfen, Aufrufer behandelt. Tests: (a) store_scenes bei fremder Projekt-DB → mark_error (Session-Fixtures), (b) set_project mit aktivem Task → Abbruch, (c) Assign ohne Reducer-Datei → Single-Bucket-Zuordnung, kein Raise. Commit: `fix(B-490,B-491): project token guard + mark_error on skip; assign-mode degraded fallback`

### CRF-011 / B-509 — Alembic-Konsolidierung

Eine neue Alembic-Revision `2026_06_12_post_baseline_consolidation`: enthält idempotent (mit `IF NOT EXISTS`-Checks via Inspector) alle Schema-Teile, die bisher nur in `database/migrations.py:415-453,607-638` leben (`locked`-Spalte, `timeline_snapshots`, `project_notes`, video_pipeline-Spalten — vorher exakt inventarisieren: models.py vs alembic-Head diffen). Legacy-Fixups in migrations.py NICHT löschen (Bestands-DBs), aber Kommentar "frozen, neue Änderungen nur via Alembic". Test: frische DB nur via Alembic aufbauen → `Base.metadata`-Vergleich (Inspector) zeigt keine fehlenden Tabellen/Spalten. Commit: `fix(B-509): alembic consolidation revision, freeze legacy fixups`

### CRF-012 / B-502 + CRF-013 / B-503 — GPU-Lock-Vereinheitlichung (zusammen ausführen, ein Agent)

(1) B-502: `workers/video.py:277-290` Modell-Loads durch `gpu_resource_lease()` (`model_manager.py:51`) führen; Deadlock-Historie beachten (Kommentar im Code erklärt warum aktuell _swap_lock-only — erst Lock-Hierarchie dokumentieren: LOAD vor EXECUTION, nie umgekehrt, dann umbauen). `services/raft_motion_service.py:56-62`: raft_large-Load in ModelManager-Aux-Slot registrieren oder mindestens unter GPU_LOAD_LOCK + VRAM-Precheck (`_handle_oom_prevention`-Pattern). (2) B-503: `services/brain_v3/gpu_serializer.py` — sync `acquire`: Timeout-Parameter (default 300 s) + Logging des aktuellen Holders bei Wartezeit > 30 s; async `_AsyncAcquireCtx.__aenter__` (Z.111-115): Lock-Acquire via `loop.run_in_executor`. Tests: Lock-Ordnungs-Contract-Test (LOAD→EXECUTION ok, Timeout greift), bestehende `test_brain_v3_gpu_serializer.py` bleibt grün. Commit: `fix(B-502,B-503): unified gpu load locking + serializer timeout/async executor`

### CRF-014 / B-510 — Audio-Skalierung 3h-Mixes

(1) `services/ai_audio_service.py:391-398`: Demucs-Input chunk-weise via `soundfile.SoundFile` (seek/read, 30-s-Chunks, Resample pro Chunk) — vorhandenen Streaming-Writer (Z.185-285) als Gegenstück nutzen; FFmpeg-Decode-Fallback (temp-WAV) bleibt. (2) `services/brain_v3/audio/subtrack_detector.py`: Z.115 `sr=None` → `sr=22050`; Z.190-196 Foote-Kernel vektorisieren (`scipy.signal.convolve2d` über Diagonale der Recurrence-Matrix) oder librosa `width`-Begrenzung; `progress_cb`+`should_stop`-Hooks einziehen (Signatur-kompatibel, Default None). Tests: numerische Äquivalenz Foote alt/neu auf 60-s-Synthetik (rtol 1e-5); Detector auf 5-min-Synthetik < bisherige Laufzeit. Commit: `fix(B-510): chunked demucs input + vectorized subtrack novelty`

## WAVE 3 — Medium (CRF-015 … CRF-023, je gleiche Mechanik)

- **CRF-015/B-511:** `np.isfinite(emb).all()`-Batch-Check in `services/video_analysis_service.py:545`-Umfeld + `brain_v3/video/video_embedder.py:287-291` (`_l2_normalize`: NaN → Scene skip + log.warning, Zähler). Test mit NaN-Injektion.
- **CRF-016/B-512:** `ui/undo_commands.py:27-67`: Python-Retry-Sleep entfernen, stattdessen `busy_timeout` (PRAGMA bereits gesetzt — prüfen warum Retry trotzdem nötig war; falls Lock-Konflikte real: Write in Worker auslagern ist out-of-scope, nur dokumentieren). Minimalziel: kein `time.sleep` im GUI-Thread.
- **CRF-017/B-513:** `workers/base.py:171-217` `run_worker()`: `owner.destroyed`-Connect → `worker.cancel()` + `thread.quit()`; Callbacks an Owner-QObject binden (Receiver-Argument in `connect`). Test: Owner löschen → kein Callback-Aufruf (Mock).
- **CRF-018/B-514:** Alembic-Revision: `Index("idx_timeline_project", timeline_entries.project_id)`, `Index("idx_hotcue_audio", hotcues.audio_track_id)` + models.py `__table_args__` synchron. (Nach CRF-011 ausführen!)
- **CRF-019/B-515:** `.gitignore`: `pb_studio.db.*`, `test_reports/`, `vendor/beat_this/build/` ergänzen; `git rm --cached` für getrackte Backup-DBs + `vendor/beat_this/build/lib/` (vorher `git ls-files` belegen). KEINE Datei von Platte löschen.
- **CRF-020/B-516:** `pyproject.toml:57-79`: F821+F811 aus Ignore-Liste nehmen → `ruff check` laufen lassen → Fehlerliste NUR dokumentieren (Bugfile-Anhang), echte F821-Treffer in Produktcode als je eigenes Folge-Bugfile. `tests/test_pacing.py` + live_*/e2e_*-Skripte nach `scripts/diag/` verschieben, pytest-Collect prüfen.
- **CRF-021/B-517:** `workers/import_export.py:417-466`: bei `-c:v copy` kein `-vf`/`-preset`; `-preset` nur für x264/x265/nvenc; `ui/controllers/convert.py:236-243`: H.264 via `detect_nvenc()` auf `h264_nvenc` mappen, Fallback libx264.
- **CRF-022/B-518:** `get_ollama_settings` aus `ui/dialogs/settings_dialog.py` nach `services/settings_store.py` verschieben (Re-Export für Alt-Importe), `services/pacing_strategist.py:293` umstellen.
- **CRF-023/B-519:** `services/brain_v3/audio/audio_embedder.py:138-162`: Fenster-Loop mit `should_stop`-Check + `progress_cb`; Audio streamend pro Fenster laden statt Full-Load; `services/beat_analysis_service.py:259` librosa-Fallback mit `MAX_DURATION`-Cap.

## WAVE 4 — Low + User-Entscheidungen

- **CRF-024/B-520:** `creationflags=CREATE_NO_WINDOW` in `convert_service.detect_nvenc` (Z.167-227) + `proxy_generator` (Z.49-88); nackte `threading.Thread` (`main.py:766-778`, `workers/structure_enrichment.py:71`) inventarisieren — Umbau nur wo trivial, Rest dokumentieren.
- **CRF-D1 (USER):** Brain v1/v2 Deprecation — Entscheidungsvorlage: was nutzt v1/v2 exklusiv, Migrationsaufwand nach v3, Embedding-Raum-Ziel (768 vs 1152). One-way door.
- **CRF-D2 (USER):** Vault-Sync (Git-Repo für C:\Brain-Bug oder Cloud-Sync). 
- **CRF-D3 (USER):** Treiber-Befund aus CRF-002 → cu121/torch-2.x-Migration ja/nein; requirements.txt-Archivierung.

## Definition of Done (pro Wave)

Alle Tasks der Wave: Code-Edit + Tests grün + Vault-Bugfile (`status: code-fix-pending-live-verification`) + log.md-Eintrag + Commit. Danach Live-Verifikations-Checkliste an User (pro Task eine konkrete Klick-Anweisung). `fixed` setzt ausschließlich der User.
