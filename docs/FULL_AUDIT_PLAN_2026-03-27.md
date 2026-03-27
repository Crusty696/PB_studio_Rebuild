# Full App Audit — Implementierungsplan (Rev. 2)

**Erstellt:** 2026-03-27
**Revision:** 2 (Gegenprüfung abgeschlossen — 19 fehlende Findings ergänzt, 6 Fehler korrigiert)
**Basis:** 6-Agenten Deep Forensic Audit (Backend, Frontend, Database, Security, Tests, Architektur)
**Codebase:** 30.432 Zeilen Python, ~80 Dateien, Version 0.5.0

---

## Zusammenfassung der Befunde

| Kategorie | Kritisch | Hoch | Mittel | Niedrig | Gesamt |
|-----------|----------|------|--------|---------|--------|
| Security | 5 | 7 | 9 | 0 | 21 |
| Database | 0 | 2 | 5 | 2 | 9 |
| Backend Services | 0 | 1 | 8 | 3 | 12 |
| Frontend/UI | 2 | 5 | 12 | 9 | 28 |
| Tests | 0 | 2 | 6 | 0 | 8 |
| Architektur | 0 | 3 | 5 | 3 | 11 |
| **Gesamt** | **7** | **20** | **45** | **17** | **89** |

---

## Baseline (VOR allen Aenderungen ausfuehren!)

```bash
# 1. Test-Baseline sichern
poetry run pytest tests/ -v --tb=short 2>&1 | tee docs/audit_2026/test_baseline_2026-03-27.txt
# Erwartung: 271 passed, 5 failed (laut Test-Agent)

# 2. App-Startzeit messen
time poetry run python -c "from main import *; print('Import OK')"

# 3. Git-Status sichern (Backend-Agent hat evtl. Dateien geaendert!)
git stash list
git diff --stat
```

> **WICHTIG:** Der Backend-Agent hat 3 Dateien geaendert (`beat_analysis_service.py`, `workers/audio_analysis.py`).
> Diese Aenderungen muessen vor Phase-Start reviewed und entweder committed oder revertet werden.

---

## Phase 0: Sofortmassnahmen (HEUTE)
> **Blocker:** Keine
> **Aufwand:** 30-45 Minuten
> **Definition of Done:** Alle 3 Tasks erledigt, App startet weiterhin

### P0-01: HuggingFace Token rotieren
- [ ] Alten Token auf https://huggingface.co/settings/tokens widerrufen
- [ ] Neuen Token mit **Read-only** Permissions erstellen
- [ ] `.env` mit neuem Token aktualisieren
- [ ] `.env.example` anlegen mit Platzhalter: `HUGGINGFACE_API_TOKEN=hf_YOUR_TOKEN_HERE`
- [ ] Verifizieren: `git log --all -p -- .env` → Token war nie im Git
- **Dateien:** `.env`, `.env.example` (neu)
- **Quelle:** Security-Agent KRIT-01

### P0-02: trust_remote_code entfernen
- [ ] `services/model_manager.py:195` — `trust_remote_code=True` entfernen (AutoTokenizer)
- [ ] `services/model_manager.py:201` — `trust_remote_code=True` entfernen (AutoModelForCausalLM)
- [ ] `services/model_manager.py:303` — `trust_remote_code=True` entfernen (Vision-Tokenizer)
- [ ] `services/model_manager.py:309` — `trust_remote_code=True` entfernen (Vision-Model)
- [ ] `revision=` Parameter mit Commit-Hash fuer Qwen und SigLIP hinzufuegen (exact Revision pinnen)
- [ ] Testen: Chat-Agent nutzen → Antwort kommt ohne Fehler
- [ ] Testen: Video-Analyse Pipeline starten → Embeddings werden generiert
- **Dateien:** `services/model_manager.py`
- **Quelle:** Security-Agent KRIT-03

### P0-03: main2457.py entfernen
- [ ] Grep: `grep -r "main2457" .` → keine Referenzen
- [ ] `main2457.py` loeschen
- [ ] Testen: `poetry run python main.py` startet korrekt
- **Dateien:** `main2457.py`
- **Quelle:** Frontend-Agent BUG-C2, Architektur-Agent Anti-Pattern 2

### P0-04: Backend-Agent Aenderungen reviewen
- [ ] `git diff workers/audio_analysis.py` pruefen (Session-Leak Fix B2, State-Coupling Fix B3)
- [ ] `git diff services/beat_analysis_service.py` pruefen (Memory-Leak Fix B1)
- [ ] Wenn korrekt: committen mit Verweis auf Audit
- [ ] Wenn nicht: revert und manuell fixen in Phase 2
- **Dateien:** `workers/audio_analysis.py`, `services/beat_analysis_service.py`
- **Quelle:** Backend-Agent B1, B2, B3

---

## Phase 1: Kritische Security-Fixes (DIESE WOCHE — Tag 1-2)
> **Blocker:** Phase 0 abgeschlossen
> **Aufwand:** 3-5 Stunden
> **Definition of Done:** Alle bekannten CVEs behoben, `poetry install` erfolgreich, alle bestehenden Tests gruen

### P1-01: PyTorch Upgrade — CVE-2025-32434 (CVSS 9.3, RCE)
- [ ] Pruefen: Existieren `cu121` Wheels fuer PyTorch 2.6.0? (`pip index versions torch --index-url https://download.pytorch.org/whl/cu121`)
- [ ] Falls nein: PyTorch Source auf `cu124` umstellen in `pyproject.toml`
- [ ] `pyproject.toml`: `torch` auf `>=2.6.0,<3.0.0`
- [ ] `pyproject.toml`: `torchvision` auf `>=0.21.0,<1.0.0`
- [ ] `pyproject.toml`: `torchaudio` auf `>=2.6.0,<3.0.0`
- [ ] `poetry lock --no-update` (nur torch-Gruppe) oder `poetry lock`
- [ ] `poetry install`
- [ ] Testen: BPM-Analyse (beat_this + torch)
- [ ] Testen: Stem-Separation (Demucs + torch)
- [ ] Testen: Video-Embeddings (SigLIP + torch)
- [ ] Testen: CPU-Fallback (`CUDA_VISIBLE_DEVICES="" python main.py`)
- **Dateien:** `pyproject.toml`, `poetry.lock`
- **Quelle:** Security-Agent KRIT-02
- **Risiko:** MITTEL — Demucs/beat_this Kompatibilitaet mit PyTorch 2.6 muss geprueft werden

### P1-02: Transformers CVEs beheben (CVE-2025-14920/14921/14924)
- [ ] Aktuelle installierte Version pruefen: `pip show transformers`
- [ ] Neueste Version ohne bekannte CVEs ermitteln (WebSearch)
- [ ] `pyproject.toml`: `transformers` Version-Constraint anpassen
- [ ] `poetry lock && poetry install`
- [ ] Testen: LLM-Agent Chat, SigLIP Embeddings
- **Dateien:** `pyproject.toml`
- **Quelle:** Security-Agent KRIT-05
- **Abhaengigkeit:** Zusammen mit P1-01 (gleicher `poetry lock`)

### P1-03: beat-this Commit-Hash pinnen
- [ ] `pyproject.toml:31`: `rev = "main"` → `rev = "c8c320e84f1a4e5b291327debe754734ea802afc"`
- [ ] `poetry lock`
- [ ] Testen: BPM-Analyse mit echtem Audio-File
- **Dateien:** `pyproject.toml`
- **Quelle:** Security-Agent HIGH-03

### P1-04: lancedb Dependency entfernen (tote Dependency)
- [ ] Grep: `grep -rn "lancedb\|lance" services/ workers/ agents/ ui/ main.py` → 0 Treffer erwartet
- [ ] `pyproject.toml`: `lancedb = "==0.30.0"` Zeile loeschen
- [ ] `poetry lock && poetry install`
- [ ] Testen: App startet, VectorDB-Suche funktioniert (nutzt eigene SQLite-Implementation)
- **Dateien:** `pyproject.toml`
- **Quelle:** Security-Agent HIGH-04, Architektur-Agent Anti-Pattern 6

### P1-05: FFmpeg stderr in Exceptions sanitisieren (NEU — fehlte im Plan)
- [ ] `services/convert_service.py:260` — Nur letzte 2 Zeilen von stderr, keine Pfade
- [ ] `services/export_service.py:470` — Analog
- [ ] `services/video_service.py:32,88,95` — Analog
- [ ] `services/ai_audio_service.py:309` — Analog
- [ ] Hilfsfunktion `_sanitize_ffmpeg_error(stderr: str) -> str` erstellen
- **Dateien:** 4 Service-Dateien
- **Quelle:** Security-Agent HIGH-01

### P1-06: Dateinamen-Validierung fuer Windows Reserved Names (NEU — fehlte im Plan)
- [ ] `services/convert_service.py:197` — `input_path.stem` auf Windows Reserved Names pruefen (`con`, `prn`, `aux`, `nul`, `com1`-`com9`, `lpt1`-`lpt9`)
- [ ] Hilfsfunktion `_safe_filename(stem: str) -> str` die Reserved Names escaped
- **Dateien:** `services/convert_service.py`
- **Quelle:** Security-Agent HIGH-06

---

## Phase 2: Datenintegritaet & DB-Fixes (DIESE WOCHE — Tag 2-3)
> **Blocker:** Keine (parallel zu Phase 1 moeglich)
> **Aufwand:** 4-6 Stunden
> **Definition of Done:** Alle DB-Integritaetstests gruen, VectorDB-Cleanup funktioniert, 0 verwaiste Records

### P2-01: VectorDB Cascade-Delete implementieren
- [ ] `services/vector_db_service.py`: Methode `delete_by_clip_ids(clip_ids: list[int])` — loescht alle Embeddings deren `id // 1_000_000` in clip_ids
- [ ] `services/vector_db_service.py`: Methode `delete_all()` — `DELETE FROM embeddings`
- [ ] `services/ingest_service.py`: In `delete_all_media()` nach Commit → `VectorDBService().delete_all()`
- [ ] `services/ingest_service.py`: In `delete_selected_media()` fuer VideoClips → `delete_by_clip_ids([clip.id for clip in to_delete])`
- [ ] Test: Media importieren → Embeddings pruefen → Media loeschen → Embeddings = 0
- **Dateien:** `services/vector_db_service.py`, `services/ingest_service.py`
- **Quelle:** Architektur-Agent 4f, P1 (kritischster DB-Befund)

### P2-02: UNIQUE Index auf beatgrids.audio_track_id
- [ ] Pre-Check: `SELECT audio_track_id, COUNT(*) FROM beatgrids GROUP BY audio_track_id HAVING COUNT(*) > 1` — muss 0 Zeilen liefern
- [ ] `database.py` in `init_db()`: `CREATE UNIQUE INDEX IF NOT EXISTS uq_beatgrids_audio_track_id ON beatgrids(audio_track_id);`
- [ ] Testen: Doppelklick auf "Analysieren" → `IntegrityError` wird abgefangen, kein Duplikat
- **Dateien:** `database.py`
- **Quelle:** DB-Agent BUG-DB-05

### P2-03: Session-Leak Fix verifizieren
- [ ] Pruefen ob Backend-Agent-Fix in `workers/audio_analysis.py` korrekt ist (P0-04)
- [ ] Alle 4 Worker (`KeyDetection`, `LUFS`, `AudioClassify`, `Spectral`) nutzen `with session:` Context-Manager
- [ ] `StructureDetectionWorker` und `SpectralAnalysisWorker` haben `self._svc = None` in `__init__`
- [ ] Testen: Audio-Analyse starten + App waehrend Analyse schliessen → kein File-Lock auf `pb_studio.db`
- **Dateien:** `workers/audio_analysis.py`
- **Quelle:** DB-Agent BUG-DB-01, Backend-Agent B2/B3

### P2-04: BPM-Update-Logik fixen
- [ ] `services/ai_audio_service.py:526`: `if not track.bpm:` → `track.bpm = result["bpm"]` (oder Prioritaetslogik)
- [ ] Test `test_analyze_and_store_updates_existing_waveform_data` muss gruen werden
- **Dateien:** `services/ai_audio_service.py`
- **Quelle:** Test-Agent Fehler 5

### P2-05: AIPacingMemory absichern
- [ ] Option A: `ForeignKey("scenes.id", ondelete="SET NULL")` auf `scene_id` + Migration
- [ ] Option B: Existenz-Check in jedem Code-Pfad der `aim.scene_id` liest
- [ ] `AIPacingMemory.created_at` von `String` auf `DateTime` aendern (semantisch falsch, verhindert Date-Queries)
- **Dateien:** `database.py`, `services/pacing_service.py`
- **Quelle:** DB-Agent BUG-DB-02, DB-Agent PERF-01 (created_at Typ)

### P2-06: SQL-Injection-Pattern in init_db() entschaerfen (NEU — fehlte im Plan)
- [ ] `database.py:549`: `col_default` in ALTER TABLE f-String wird nicht validiert
- [ ] Fix: `col_default` durch denselben Regex wie `stem_col` validieren (`r"^[a-z0-9_.]+$"`)
- [ ] Oder: Parameterisierte DDL-Konstrukte nutzen
- **Dateien:** `database.py`
- **Quelle:** DB-Agent BUG-DB-03

### P2-07: DetachedInstanceError-Risiko in _get_scenes() (NEU — fehlte im Plan)
- [ ] `services/pacing_service.py:250-259`: ORM-Objekte nach Session-Close zurueckgegeben
- [ ] Fix: Dataclass `SceneSnapshot` statt rohe ORM-Objekte zurueckgeben
- [ ] Oder: `session.expunge_all()` vor Return (weniger sauber)
- **Dateien:** `services/pacing_service.py`
- **Quelle:** DB-Agent BUG-DB-04

---

## Phase 3: Thread-Safety & UI-Stabilitaet (DIESE WOCHE — Tag 3-5)
> **Blocker:** Phase 0 abgeschlossen
> **Aufwand:** 5-8 Stunden
> **Definition of Done:** Kein UI-Freeze bei parallelen Analysen, sauberes closeEvent, kein Thread-Safety-Verstoss

### P3-01: VideoPreviewWidget Cleanup in closeEvent
- [ ] `main.py` in `closeEvent()`: VOR `super().closeEvent(event)`:
  ```python
  if hasattr(self, 'video_preview'):
      self.video_preview.stop()
  ```
- [ ] Testen: App mit laufender Preview schliessen → kein OperationalError im Log
- **Dateien:** `main.py`
- **Aufwand:** 5 Minuten
- **Quelle:** Frontend-Agent BUG-C1

### P3-02: Lambda-Signal-Slots absichern (22 Stellen)
- [ ] Grep: `grep -n "\.connect(lambda" main.py` → alle 22 Stellen identifizieren
- [ ] **Prioritaet 1 (sofort):** Die 5 Lambda-Slots die DB-Zugriffe oder `_refresh_media_table()` aufrufen
- [ ] **Prioritaet 2:** Alle verbleibenden 17 Lambda-Slots
- [ ] Fuer jede: Benannten Slot erstellen ODER `Qt.ConnectionType.QueuedConnection` hinzufuegen
- [ ] Testen: 3 parallele Audio-Analysen starten → Console-Output korrekt, kein Freeze
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent THREAD-1

### P3-03: Timeline DB-Write aus Main Thread auslagern
- [ ] `ui/timeline.py:491-506`: `_flush_pending_move()` → DB-Write in `QRunnable` oder Worker
- [ ] `clip_moved` Signal erst nach erfolgreichem DB-Write emittieren
- [ ] Testen: Timeline-Clips schnell hin- und herziehen → kein Stutter
- **Dateien:** `ui/timeline.py`
- **Quelle:** Frontend-Agent BUG-C3

### P3-04: N+1 Queries bei add_clip() und Anchor-Dialog fixen
- [ ] `main.py:1461`: `add_clip()` mit `anchors=` Parameter aufrufen (Bulk-Load statt einzeln)
- [ ] `main.py:1158-1170`: `joinedload(VideoClip.scenes)` in der Query:
  ```python
  clips = session.query(VideoClip).options(joinedload(VideoClip.scenes)).filter_by(project_id=1).all()
  ```
- **Dateien:** `main.py`, `ui/timeline.py`
- **Quelle:** Frontend-Agent BUG-C4, BUG-C6

### P3-05: Confirmation-Dialog bei Close mit laufenden Tasks (NEU — fehlte im Plan)
- [ ] `main.py` `closeEvent()`: Pruefen ob Tasks laufen via `GlobalTaskManager`
- [ ] Falls ja: `QMessageBox.question("Analyse laeuft noch. Trotzdem beenden?")`
- [ ] Bei "Nein": `event.ignore()` und zurueck
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent UX-6

### P3-06: AIAgentWorker Registry-Lock absichern (NEU — fehlte im Plan)
- [ ] `ui/chat_dock.py:100-112`: `_registry_lock` um den gesamten Block (inklusive `process()`) legen
- [ ] Oder: Kopie der Registry fuer den Worker-Thread erstellen statt die Original-Referenz zu swappen
- **Dateien:** `ui/chat_dock.py`
- **Quelle:** Frontend-Agent THREAD-3

### P3-07: Silent Worker Failures sichtbar machen (NEU — fehlte im Plan)
- [ ] `main.py` `_start_worker_thread()`: Fallback-`finished`-Signal verknuepfen das prüft ob `error` emittiert wurde
- [ ] Wenn ein Worker intern crasht ohne `self.error.emit()`: Task als "error" im TaskManager markieren
- [ ] Optional: `QThread.finished` Signal als Safety-Net nutzen
- **Dateien:** `main.py`, `services/task_manager.py`
- **Quelle:** Frontend-Agent ERR-1

### P3-08: Unsichtbare Proxy-Tabelle — User-Feedback bei fehlender Selektion (NEU — fehlte im Plan)
- [ ] `main.py:1418-1426`: `_add_selected_to_timeline()` — Warnung NICHT nur in Console sondern auch in StatusBar oder MessageBox anzeigen
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent BUG-C5

---

## Phase 4: VRAM-Koordination & Performance (NAECHSTE WOCHE — Tag 6-8)
> **Blocker:** Phase 1 (PyTorch Upgrade) abgeschlossen
> **Aufwand:** 6-10 Stunden
> **Definition of Done:** Kein OOM bei parallelen GPU-Tasks auf GTX 1060, App-Start < 3s bis UI sichtbar

### P4-01: GPU-Modelle vereinheitlichen (3 → 1 System)
- [ ] **Analyse:** Aktuelle VRAM-Nutzung messen (BeatAnalysis, Demucs, SigLIP einzeln)
- [ ] **Option A (empfohlen):** Alle in ModelManager integrieren
  - [ ] `ModelManager.load_beat_this()` Methode
  - [ ] `ModelManager.load_demucs()` Methode
  - [ ] `BeatAnalysisService._model` → `ModelManager.get_beat_this()`
  - [ ] `StemSeparator._separator` → `ModelManager.get_demucs()`
  - [ ] `_swap_lock` schuetzt automatisch vor parallelem Laden
- [ ] **Option B:** GPU-Semaphore in GlobalTaskManager (max 1 GPU-Task gleichzeitig)
- [ ] Silent Failures eliminieren (4 Stellen):
  - [ ] `ai_audio_service.py:65` — `except Exception: pass` → `logger.warning("ModelManager unload failed: %s", e)`
  - [ ] `beat_analysis_service.py:60` — analog
  - [ ] `beat_analysis_service.py:86` — analog
  - [ ] `beat_analysis_service.py:319` — analog
- [ ] Testen: Stem-Separation + BPM-Analyse + Video-Embeddings nacheinander → kein OOM
- [ ] Testen: Gleichzeitiger Start von 2 GPU-Tasks → serialisiert oder sauber abgelehnt
- **Dateien:** `services/model_manager.py`, `services/beat_analysis_service.py`, `services/ai_audio_service.py`
- **Quelle:** Architektur-Agent 4b, Anti-Pattern 3, Backend-Agent W3

### P4-02: Torch-Import lazy machen (Startup-Blockade)
- [ ] `services/local_agent_service.py`: `ModelManager()` NICHT im `__init__` aufrufen
- [ ] Lazy Property:
  ```python
  @property
  def model_manager(self):
      if self._model_manager is None:
          self._model_manager = ModelManager()
      return self._model_manager
  ```
- [ ] Alle Zugriffe auf `self.model_manager` pruefen (kein direkter `__init__`-Zugriff mehr)
- [ ] Testen: App-Startzeit messen (Ziel: < 3s bis UI sichtbar, vorher ~11s)
- **Dateien:** `services/local_agent_service.py`
- **Quelle:** Architektur-Agent 4e, 5

### P4-03: DEBUG-Logging auf INFO setzen
- [ ] `main.py:2643,2652,2660`: `logging.DEBUG` → `logging.INFO`
- [ ] Optional: `--verbose` CLI-Flag fuer DEBUG
- [ ] `local_agent_service.py:370`: KI-Rohantwort bleibt auf `DEBUG` (wird nicht mehr ausgegeben)
- **Dateien:** `main.py`
- **Quelle:** Security-Agent HIGH-05

### P4-04: _refresh_media_table() Debouncing
- [ ] Debounce-Timer: `QTimer.singleShot(200, ...)` mit Flag das Mehrfach-Aufrufe verhindert
- [ ] Oder: Differentielles Update (nur geaenderte Zeilen in Pool-Tabellen)
- [ ] Testen: 10 Worker nacheinander fertig → nur 1 Table-Rebuild statt 10
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent PERF-1

### P4-05: _build_media_context() Caching (NEU — fehlte im Plan)
- [ ] `services/local_agent_service.py:167-200`: DB-Query bei jedem LLM-Aufruf
- [ ] Fix: 30-Sekunden-Cache mit `time.monotonic()` Invalidierung
- **Dateien:** `services/local_agent_service.py`
- **Quelle:** Backend-Agent CS3

### P4-06: QFont-Objekte cachen (NEU — fehlte im Plan)
- [ ] `ui/timeline.py:477`: `QFont("Segoe UI", 7)` als Klassen-Konstante statt pro Tick neu erstellen
- **Dateien:** `ui/timeline.py`
- **Quelle:** Frontend-Agent PERF-3

---

## Phase 5: Test-Bereinigung & Coverage (NAECHSTE WOCHE — Tag 8-12)
> **Blocker:** Phase 2 & 3 sollten abgeschlossen sein
> **Aufwand:** 10-16 Stunden
> **Definition of Done:** Alle Tests gruen, Coverage von 59% auf 80%+ Services, Worker-Basis-Tests vorhanden

### P5-01: 5 fehlschlagende Tests fixen
- [ ] **4x Orchestrator API-Mismatch:** `tests/test_agents/test_orchestrator.py:117-176`
  - [ ] `_handle_compound_actions` Signatur in `orchestrator_agent.py:365` pruefen
  - [ ] Entweder `(self, text, action_names)` wiederherstellen ODER Tests anpassen
  - [ ] Dokumentieren warum `text`-Parameter entfiel/hinzukam
- [ ] **1x BPM-Update:** Wird durch P2-04 gefixt
- [ ] `pytest tests/ -v` → 276 passed, 0 failed
- **Dateien:** `agents/orchestrator_agent.py` oder `tests/test_agents/test_orchestrator.py`
- **Quelle:** Test-Agent Fehler 1-5

### P5-02: Fake-Tests & Duplikate bereinigen
- [ ] `tests/test_pacing.py` → Umbenennen zu `scripts/pacing_demo.py` ODER in echten pytest umwandeln
- [ ] `tests/test_unit_swarm.py` → Analog
- [ ] `tests/smoke_test_app.py` → Echte Assertions hinzufuegen (mindestens 5) ODER entfernen
- [ ] Duplikate loeschen:
  - [ ] `tests/test_ingest_service.py` (ersetzt durch `tests/test_services/test_ingest_service.py`)
  - [ ] `tests/test_video_service.py` (ersetzt durch `tests/test_services/test_video_service.py`)
  - [ ] `tests/test_action_registry.py` (ersetzt durch `tests/test_agents/test_action_registry.py`)
- [ ] `pytest tests/ -v` → alle gruen, keine Skript-Ausfuehrung auf Modul-Ebene
- **Dateien:** 6 Test-Dateien
- **Quelle:** Test-Agent 4.2, 4.4

### P5-03: conftest.py Engine-Patching erweitern (NEU — fehlte im Plan)
- [ ] `tests/conftest.py`: Engine-Patching-Liste um fehlende Module erweitern:
  - [ ] `export_service`
  - [ ] `structure_detection_service`
  - [ ] `vector_db_service`
  - [ ] `timeline_service`
  - [ ] `convert_service`
  - [ ] `beat_analysis_service`
- [ ] Damit neue Tests diese Module automatisch mit In-Memory-DB testen
- **Dateien:** `tests/conftest.py`
- **Quelle:** Test-Agent 1.1

### P5-04: Kritische Service-Tests schreiben
- [ ] `tests/test_services/test_export_service.py`:
  - [ ] `export_timeline()` mit Mock-FFmpeg
  - [ ] `_export_optimized_concat()` Pfad
  - [ ] Timeline-Aufbau mit In-Memory-DB
- [ ] `tests/test_services/test_beat_analysis.py`:
  - [ ] `analyze_and_store()` mit Fixture-Audio
  - [ ] UNIQUE-Constraint-Test (Doppel-Insert)
- [ ] `tests/test_services/test_convert_service.py`:
  - [ ] FFmpeg-Preset-System
  - [ ] NVENC-Detection Mock
- [ ] `tests/test_services/test_timeline_service.py`:
  - [ ] OTIO Timeline-Export
- [ ] `tests/test_services/test_task_manager.py`:
  - [ ] Worker-Start, Progress-Signale, Error-Handling
- [ ] `tests/test_services/test_vector_db.py`:
  - [ ] add_embeddings_batch + search + delete_by_clip_ids
- [ ] `tests/test_services/test_video_analysis.py` (NEU — 767 Zeilen komplett ungetestet!):
  - [ ] SigLIP-Embedding-Generation (Mock-Modell)
  - [ ] Scene-Detection Logik
  - [ ] store_scenes_in_db()
- **Dateien:** 7 neue Test-Dateien
- **Quelle:** Test-Agent Coverage Map

### P5-05: Worker-Basis-Tests schreiben (NEU — fehlte im Plan, 0% Coverage!)
- [ ] `tests/test_workers/test_analysis_worker.py`:
  - [ ] AnalysisWorker mit Mock-AudioAnalyzer
  - [ ] Error-Pfad: Was passiert bei Exception in `run()`?
- [ ] `tests/test_workers/test_video_worker.py`:
  - [ ] FrameExtractWorker mit Test-Video
  - [ ] Batch-Pipeline-Worker Grundtest
- [ ] `tests/test_workers/test_audio_analysis_workers.py`:
  - [ ] KeyDetection, LUFS, Spectral, AudioClassify Worker-Tests
  - [ ] Session-Handling korrekt? (Context-Manager nach Fix)
- **Dateien:** 3 neue Test-Dateien
- **Quelle:** Test-Agent Coverage Map (0% Worker-Coverage)

---

## Phase 6: UI-Polish & Theme-Konsistenz (WOCHE 3)
> **Blocker:** Phase 3 abgeschlossen
> **Aufwand:** 5-8 Stunden
> **Definition of Done:** Einheitliches Gold-Accent Theme, keine Hard-coded Farben, alle Stub-Buttons dokumentiert/deaktiviert

### P6-01: Theme-Inkonsistenzen beheben (5 Stellen)
- [ ] `ui/widgets/task_manager_dock.py:50-67` — `#1E1E1E`/`#3A1010` → Theme-Variablen
- [ ] `ui/timeline.py:173-176` — Context-Menu → App-Stylesheet erben
- [ ] `ui/chat_dock.py:178-186` — `#D4AF37` → `{ACCENT}` aus theme.py
- [ ] `ui/dialogs/about.py:40` — `#1a1b23` → Theme BG-Wert
- [ ] `ui/workspaces/convert_workspace.py:114-117` — Inline-Style entfernen
- **Dateien:** 5 UI-Dateien
- **Quelle:** Frontend-Agent THEME-1 bis THEME-5

### P6-02: RL-Feedback-Stubs mit Backend verbinden oder deaktivieren
- [ ] `main.py:1357-1365`: `_rl_feedback_positive/negative`
- [ ] Option A: Mit `AIPacingMemory.learn_from_anchor()` verbinden
- [ ] Option B: Buttons als `setEnabled(False)` + Tooltip "Coming soon"
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent BUG-C7

### P6-03: Slider-Aliasing aufloesen
- [ ] `ui/workspaces/edit_workspace.py:213-216`: `tempo_slider = energy_slider = density_slider`
- [ ] Entweder 3 separate Slider ODER alle Referenzen auf den einen kanonischen Namen aendern
- **Dateien:** `ui/workspaces/edit_workspace.py`
- **Quelle:** Frontend-Agent UX-1

### P6-04: Solo-Button implementieren oder entfernen
- [ ] `ui/widgets/stem_workspace.py:385-408`: Solo-Signal → andere Tracks muten
- [ ] Oder: Button entfernen wenn nicht geplant
- **Dateien:** `ui/widgets/stem_workspace.py`
- **Quelle:** Frontend-Agent UX-4

### P6-05: Anker-Dialog Sub-Sekunden-Genauigkeit
- [ ] `main.py:1145-1147`: `QSpinBox` → `QDoubleSpinBox(decimals=3, singleStep=0.1)`
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent UX-5

### P6-06: btn_mode_audio Signal verbinden (NEU — fehlte im Plan)
- [ ] `ui/workspaces/media_workspace.py:198`: Auch `btn_mode_audio.toggled` explizit verbinden
- [ ] Nicht auf fragile AutoExclusive-Kopplung verlassen
- **Dateien:** `ui/workspaces/media_workspace.py`
- **Quelle:** Frontend-Agent UX-2

### P6-07: Console-Bereich und Fehler-Indikator verbessern (NEU — fehlte im Plan)
- [ ] `main.py:241-243`: Splitter-Size so anpassen dass Console bei allen DPI-Skalierungen lesbar
- [ ] Fehler-Counter in StatusBar oder NavBar anzeigen ("3 Fehler" Badge)
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent UX-3

### P6-08: Timeline ↔ Video Preview Synchronisation (NEU — fehlte im Plan)
- [ ] `main.py:_on_timeline_clip_moved()` — Video-Preview zur neuen Position springen lassen
- [ ] Bei Clip-Selektion in Timeline: Preview-Frame zeigen
- **Dateien:** `main.py`
- **Quelle:** Frontend-Agent CROSS-2

---

## Phase 7: Architektur-Verbesserungen (WOCHE 3-4)
> **Blocker:** Phase 4 & 5 abgeschlossen
> **Aufwand:** 12-24 Stunden (optional, langfristig)
> **Definition of Done:** Sauberere Schichtung, kein God Object, keine Legacy-Threads

### P7-01: PBWindow God Object aufbrechen
- [ ] `EditController` extrahieren (Edit-Workspace Logik, ~300 Zeilen)
- [ ] `MediaController` extrahieren (Import/Export/Pool Logik, ~400 Zeilen)
- [ ] `AnalysisController` extrahieren (Audio/Video-Analyse Logik, ~500 Zeilen)
- [ ] PBWindow nur noch als Wiring-Hub (Signal/Slot Connections)
- [ ] Alle Tests weiterhin gruen
- **Dateien:** `main.py` → 3-4 neue Controller-Dateien
- **Risiko:** HOCH — viele Abhaengigkeiten
- **Quelle:** Frontend-Agent CROSS-1, Architektur-Agent Anti-Pattern 1

### P7-02: Legacy-Thread-Management entfernen
- [ ] `_active_threads` / `_active_workers` durch GlobalTaskManager ersetzen
- [ ] `_start_worker_thread()` Bridge auf `GlobalTaskManager.start_task()` umstellen
- [ ] `_GLOBAL_ACTIVE_THREADS` globale Liste entfernen
- **Dateien:** `main.py`
- **Quelle:** Architektur-Agent 4a

### P7-03: init_db() Refactoring
- [ ] 150-Zeilen-Monolith in separate Migrations-Funktionen aufteilen
- [ ] Optional: Alembic fuer formelles Migration-Management
- **Dateien:** `database.py`
- **Quelle:** Test-Agent 5.1

### P7-04: created_at/updated_at auf alle Tabellen
- [ ] 13 Tabellen ohne Timestamps → `Column(DateTime, default=func.now())`
- [ ] Migration fuer bestehende DBs in `init_db()`
- **Dateien:** `database.py`
- **Quelle:** DB-Agent PERF-01

### P7-05: stem_player.py von Qt-Dependencies befreien (NEU — fehlte im Plan)
- [ ] `services/stem_player.py` importiert `PySide6.QtMultimedia` — Schichten-Verstoss
- [ ] Audio-Playback-Logik in Qt-agnostischen Service auslagern
- [ ] Qt-Widget-Wrapper in `ui/widgets/` fuer die UI-Integration
- **Dateien:** `services/stem_player.py` → aufteilen
- **Quelle:** Test-Agent 6.1, Architektur-Agent (Schichten-Verletzung)

### P7-06: pacing_service.py aufteilen (NEU — fehlte im Plan)
- [ ] 1712 Zeilen → natuerliche Grenzen:
  - [ ] `services/beat_grid_utils.py` (Beat-Grid-Hilfsfunktionen)
  - [ ] `services/cut_point_calculator.py` (Cut-Point-Algorithmen)
  - [ ] `services/auto_edit_engine.py` (Auto-Edit Logik)
- **Dateien:** `services/pacing_service.py` → 3-4 Dateien
- **Quelle:** Test-Agent 5.3

### P7-07: ChatDock Entkopplung (NEU — fehlte im Plan)
- [ ] `ui/chat_dock.py:360-381`: Direkte `self._main_window` Referenz ersetzen
- [ ] Signal-basierte Kommunikation statt direkter Methoden-Aufrufe
- **Dateien:** `ui/chat_dock.py`
- **Quelle:** Frontend-Agent CROSS-4

### P7-08: FFmpeg vf_extra Validierung
- [ ] `main.py:736`: `brightness`/`contrast` als `float()` casten mit Bereichspruefung
- [ ] `workers/video.py:296`: Whitelist-Validierung fuer `vf_extra`
- **Dateien:** `main.py`, `workers/video.py`
- **Quelle:** Security-Agent KRIT-04

### P7-09: File-Extension-Pruefung bei Import
- [ ] `services/ingest_service.py`: Vor `ffprobe`-Aufruf Extension gegen `AUDIO_EXTENSIONS`/`VIDEO_EXTENSIONS` pruefen
- **Dateien:** `services/ingest_service.py`
- **Quelle:** Security-Agent HIGH-07

---

## Backlog (Niedrige Prioritaet — wenn Zeit)

| ID | Problem | Datei | Quelle |
|----|---------|-------|--------|
| BL-01 | `Project.path = "."` relatives Pfad-Problem | `database.py:592` | DB-Agent DB-07 |
| BL-02 | `PacingCurveWidget` klippt bei < 900px Fensterhoehe | `ui/widgets/pacing_curve.py` | Frontend-Agent LIFE-2 |
| BL-03 | Keine Keyboard-Navigation fuer NavBar | `ui/widgets/nav_bar.py` | Frontend-Agent ACCESS-1 |
| BL-04 | Kein Delete-Key/Doppelklick-Edit fuer Anker-TreeWidget | `ui/workspaces/edit_workspace.py:251` | Frontend-Agent ACCESS-2 |
| BL-05 | `WaveformGraphicsItem._tile_cache` falscher "thread-safe" Kommentar | `ui/waveform_item.py:75` | Frontend-Agent PERF-2 |
| BL-06 | `StemPlayer` Ownership-Kette unsauber (Kind von MediaWorkspace, Ref von PBWindow) | `main.py:339`, `media_workspace.py:187` | Frontend-Agent LIFE-1 |
| BL-07 | `StemPlayer._audio_callback` macht Disk-I/O im Realtime-Callback | `services/stem_player.py:391-411` | Backend-Agent CS2 |
| BL-08 | `LocalAgentService._generate()` erstellt ThreadPoolExecutor pro Aufruf | `services/local_agent_service.py:232-241` | Backend-Agent CS1 |
| BL-09 | `AudioAgent.can_handle()` Score zu breit (false positives) | `agents/audio_agent.py:54-59` | Backend-Agent CS4 |
| BL-10 | Fragile Batch-Erkennung via Tuple-Laenge in VideoWorker | `workers/video.py:139` | Backend-Agent W1 |
| BL-11 | Beat-Intervall-Schaetzung `beats[1]-beats[0]` fragil | `services/pacing_service.py:~623` | Backend-Agent W2 |
| BL-12 | AutoDucker.create_ducked_audio() unterdrueckt Progress-Events | `services/ai_audio_service.py:315` | Backend-Agent W3 |
| BL-13 | `base_cut_rate` Schema "number" aber erwartet `int` | `services/register_actions.py` | Backend-Agent W4 |
| BL-14 | Emoji-Zeichen in Orchestrator-Agent Strings | `agents/orchestrator_agent.py:248,258` | Backend-Agent W5 |
| BL-15 | Kein FFmpeg PATH-Check beim App-Start | `services/convert_service.py:34-35` | Architektur-Agent 4d |
| BL-16 | Kein Crash-Recovery / Auto-Save Feature | — | Architektur-Agent 6 |
| BL-17 | `__init__.py` Exporte nie genutzt (leere Packages) | `agents/`, `services/`, `ui/` | Architektur-Agent Anti-Pattern 7 |
| BL-18 | `register_actions.py` 1045 Zeilen (deklarativ, sollte Config sein) | `services/register_actions.py` | Test-Agent 5.5 |
| BL-19 | `Empty-Segments-Pfad` in _on_auto_edit_finished nicht vollstaendig abgesichert | `main.py:988-993` | Frontend-Agent ERR-2 |

---

## Validierungsplan (nach JEDER Phase)

### Automatisierte Checks
```bash
# Pflicht nach jeder Phase:
poetry run pytest tests/ -v --tb=short 2>&1 | tee docs/audit_2026/test_phase_N.txt
poetry run python -c "from database import init_db; init_db(); print('DB OK')"
poetry run python -c "import services.model_manager; print('Import OK')"

# Nach Phase 1 zusaetzlich:
poetry run python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA {torch.cuda.is_available()}')"

# Nach Phase 5 zusaetzlich:
poetry run pytest tests/ -v --tb=short -q | grep -E "passed|failed|error"
```

### Manuelle Checks (nach jeder Phase ausfuehren)
- [ ] App starten → kein Crash, UI sichtbar
- [ ] Audio importieren → Analyse starten → BPM/Key in Tabelle sichtbar
- [ ] Video importieren → Pipeline → Scenes + Embeddings in DB
- [ ] Media loeschen → VectorDB-Eintraege geloescht
- [ ] Auto-Edit → Timeline korrekt aufgebaut
- [ ] Export → Ausgabe-Video spielbar (ffplay/VLC)
- [ ] App schliessen → kein Error im Log, kein `pb_studio.db-wal` File-Lock

### Regression-Checks (am Ende)
- [ ] Vergleich mit Baseline: `diff docs/audit_2026/test_baseline.txt docs/audit_2026/test_phase_N.txt`
- [ ] Keine neuen Failures eingefuehrt
- [ ] App-Startzeit gemessen und dokumentiert

---

## Abhaengigkeitsgraph

```
Phase 0 (Sofort, 45min) ─────────────────────────────┐
   │                                                    │
   ├── Phase 1 (Security, Tag 1-2) ──────┐             │
   │      │                               │             │
   │      └── Phase 4 (VRAM/Perf, W2) ───┤             │
   │             │                        │             │
   │             └── Phase 7 (Arch, W3-4) │             │
   │                                      │             │
   ├── Phase 2 (DB-Fixes, Tag 2-3) ──────┼── Phase 5 (Tests, W2)
   │                                      │
   └── Phase 3 (Thread-Safety, Tag 3-5) ──┘
          │
          └── Phase 6 (UI-Polish, W3)
```

- Phase 0 → alles andere
- Phase 1 → Phase 4 (PyTorch muss zuerst upgegradet sein)
- Phase 2 + 3 → Phase 5 (Fixes muessen drin sein bevor neue Tests geschrieben werden)
- Phase 3 → Phase 6 (Thread-Safety vor UI-Polish)
- Phase 4 + 5 → Phase 7 (Architektur erst wenn Basis stabil)

---

## Metriken & Ziele

| Metrik | IST (vor Audit) | ZIEL (nach Phase 5) | ZIEL (nach Phase 7) |
|--------|-----------------|---------------------|---------------------|
| Tests passed | 271/276 (98.2%) | 276/276 (100%) | 300+/300+ (100%) |
| Services mit Tests | 13/22 (59%) | 20/22 (91%) | 22/22 (100%) |
| Workers mit Tests | 0/8 (0%) | 3/8 (38%) | 8/8 (100%) |
| Bekannte CVEs | 4 aktiv | 0 | 0 |
| Silent Failures | 4 Stellen | 0 | 0 |
| Lambda-Slot-Risiken | 22 unsicher | 0 | 0 |
| App-Startzeit (bis UI) | ~11s | < 3s | < 2s |
| Theme-Inkonsistenzen | 5 | 5 (Phase 6) | 0 |
| God Object (main.py) | 2732 Zeilen | 2732 | < 800 Zeilen |

---

## Skills-Zuordnung

| Phase | Primaer-Skills | Sekundaer-Skills |
|-------|---------------|-----------------|
| 0 | security-officer | — |
| 1 | dependency-guard | gpu-optimizer, security-officer |
| 2 | database-admin | test-engineer, error-handling |
| 3 | gui-specialist, gui-wiring | error-handling |
| 4 | gpu-optimizer, performance-profiler | service-layer |
| 5 | test-engineer | code-auditor |
| 6 | ux-designer | gui-specialist |
| 7 | system-architect, senior-refactorer | database-admin, gui-wiring |

---

## Revision History

| Rev | Datum | Aenderungen |
|-----|-------|-------------|
| 1 | 2026-03-27 | Erstversion aus 6-Agenten-Audit |
| 2 | 2026-03-27 | +19 fehlende Findings ergaenzt, 6 Fehler korrigiert, Baseline/Metriken/DoD hinzugefuegt, Backlog mit 19 Items, conftest-Fix, Worker-Tests, Video-Analysis-Tests |
