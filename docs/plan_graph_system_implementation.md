# Implementierungsplan: Graph-basiertes Wissens- & Ähnlichkeitssystem

**Version:** 1.0 — Verifiziert gegen realen Code
**Datum:** 2026-04-14
**Grundlage:** `machbarkeitsstudie_graph_system.md` (verifiziert + korrigiert)
**Status:** Planung abgeschlossen, Implementierung ausstehend
**Ziel-venv:** `.venv310` (Python 3.10.11, PySide6 6.7.3)

---

## 0. Executive Summary

**Verdikt: GO — mit angepasster Versions-Basis.**

Die Machbarkeitsstudie wurde gegen den realen Code verifiziert. Alle zentralen Architektur-Claims stimmen: `VectorDBService`, `ModelManager`, Pacing-Pipeline, DB-Schema, Panel-System und QDockWidget-Muster sind vorhanden und kompatibel. Drei Fehler der Studie sind korrigiert:

1. **Versions-Ist-Zustand:** PB Studio läuft auf Python 3.10.11 + PySide6 6.7.3 in `.venv310` (nicht 3.11.9 / 6.11.0 wie Studie behauptet). Alle Versions-Pins in diesem Plan berücksichtigen das.
2. **Kein separates `PySide6-WebEngine`-Paket.** QtWebEngine ist bereits in `PySide6_Addons==6.7.3` integriert und in `.venv310` vorinstalliert (Qt6WebEngineCore.dll 149 MB, QtWebEngineProcess.exe, QtWebEngineWidgets.pyd). Keine Pip-Installation nötig.
3. **PyInstaller-Aufwand unterschätzt.** `pb_studio.spec` hat aktuell **keine** WebEngine-Einträge. Das ist der größte Einzel-Risikopunkt der gesamten Integration (siehe Sektion 5.3).

**Modell-Abhängigkeiten:** SigLIP, Demucs, beat_this, RAFT, Moondream2/Gemma bleiben unberührt. Der Graph liest nur bestehende Datenstrukturen (Scenes, Embeddings, StructureSegments) und greift nicht in Modell-Inferenz ein.

**Aufwand:**
- **Phase 0 (Spike/Go-No-Go):** 2 Arbeitstage
- **Phase 1 (MVP):** 8–10 Arbeitstage
- **Phase 2 (Vollausbau):** weitere 10–14 Arbeitstage (nur nach bestätigtem Nutzen)

**Risiko-Einstufung:** MITTEL (3/5) — dominiert durch PyInstaller+WebEngine auf Windows.

---

## 1. Verifizierte Architektur-Landkarte

Alle folgenden Befunde sind belegt mit `datei.py:zeile`. Sie bilden die Ankerpunkte für jede einzelne Aufgabe in den Folgeabschnitten.

### 1.1 UI-Shell

| Komponente | Datei:Zeile | Rolle |
|---|---|---|
| Hauptfenster | `main.py:177-299` | `PBWindow(QMainWindow)` — orchestriert alle Controller |
| Workspace-Stack | `main.py` in `PBWindow.__init__` | `QStackedWidget` mit 5 Workspaces (MEDIA/EDIT/STEMS/CONVERT/DELIVER) |
| Panel-Orchestrierung | `ui/controllers/panel_setup.py:13-143` | `PanelSetupController` richtet Docks ein |
| Existierendes Dock-Muster | `ui/controllers/panel_setup.py:70-127` | `setup_chat_dock()` — Chat als `QDockWidget` rechts, Lazy-Init via `QTimer` |
| Console-Dock | `ui/controllers/panel_setup.py:31-68` | TaskDock + Console im unteren Splitter, 250 ms Flush-Rate (F-034) |
| Edit-Workspace | `ui/workspaces/edit_workspace.py` (über `workspace_setup.py:147+`) | Ziel-Ort für Graph-Panel als neues Tab |

**Einhäng-Optionen für Graph-Panel:**
- **Option A (empfohlen):** Neues `QDockWidget` analog zum Chat-Dock, linkes oder rechtes Panel, über `PBWindow.addDockWidget()`. Vorteil: abkoppelbar, user-toggleable.
- **Option B:** Neues Tab innerhalb `EditWorkspace`. Vorteil: immer sichtbar wenn in EDIT-Workspace. Nachteil: begrenzter Platz.
- **Option C:** Eigener Workspace „GRAPH" im `QStackedWidget`. Nachteil: zu prominent für MVP.

### 1.2 Service-Lifecycle

| Fact | Datei:Zeile |
|---|---|
| Singleton-Muster (Referenz für GraphService) | `services/vector_db_service.py:45-71` |
| Singleton-Thread-Lock | `services/vector_db_service.py:42` (`_instance_lock`) |
| In-Memory-Cache-Pattern | `services/vector_db_service.py:64-66` |
| Projekt-Switch-Orchestrator | `database/session.py:306-332` (`set_project()`) |
| Service-Reset-Mechanik | `database/session.py:283-303` (`_patch_service_paths()`) |
| Global Lock | `database/session.py:22` (`_APP_ROOT_LOCK` = `RLock`) |
| ModelManager GPU-Locks | `services/model_manager.py:41,46` (`GPU_LOAD_LOCK`, `GPU_EXECUTION_LOCK`) |

**Konsequenz:** `GraphService` muss im gleichen Singleton-Muster gebaut und in `_patch_service_paths()` beim Projekt-Switch zurückgesetzt werden (Zeile 283-303 erweitern).

### 1.3 Pacing-Pipeline Integrations-Punkte

| Funktion | Datei:Zeile | Rolle für Graph |
|---|---|---|
| `_match_video_for_segment()` | `services/pacing_edit_helpers.py:896-914` | **Haupteinstiegspunkt für Anti-Repetition.** Signatur-End: returnt `(video_id, source_start, clip_idx)` |
| `used_recently`-Filter | `services/pacing_edit_helpers.py:962` | **Natürlicher Hook-Point** — Graph-Distanz-Filter direkt danach |
| CrossModalMatcher | `services/pacing_edit_helpers.py:970` | Aktuelles Fitness-Scoring (bleibt unangetastet) |
| Fallback-Fitness | `services/pacing_edit_helpers.py:987` (`_compute_clip_fitness()`) | Bleibt unangetastet |
| AI-Memory | `services/pacing_memory.py:139-165` (`record_rl_feedback()`) | Ziel für erweiterte Reward-Funktion (Phase 2) |
| Pacing-Settings | `services/pacing_beat_grid.py:115-126` (`AdvancedPacingSettings`) | Erweitern um Graph-Felder |
| Strategist | `services/pacing_strategist.py:68-124` | Keine Änderung nötig |

### 1.4 DB-Schema

| Modell-Klasse | Datei:Zeile | Graph-Relevanz |
|---|---|---|
| `VideoClip` | `database/models.py:91-116` | Top-Level-Container |
| `Scene` | `database/models.py:119-140` | **Video-Knoten** (id, video_clip_id, start/end_time, label, energy, ai_caption, ai_mood, ai_tags) |
| `Beatgrid` | `database/models.py:143+` | **Beat-Knoten** (tempo, beat_positions, energy_per_beat) |
| `StructureSegment` | `database/models.py:302-320` | **Section-Knoten** (label INTRO/DROP/BREAKDOWN) |
| `AudioTrack` | `database/models.py:42-88` | Audio-Metadaten |
| `AIPacingMemory` | `database/models.py:263-299` | Memory-Knoten (Phase 2) |

**Embeddings (separate DB):**
- Pfad: `data/vector/embeddings.db` (`services/vector_db_service.py:23`)
- Tabelle `clip_embeddings`: `id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding (BLOB 1152-dim)`

### 1.5 Infrastruktur

| Element | Datei:Zeile | Kern-Fakt |
|---|---|---|
| Start-Script | `start_pb_studio.py:14-18` | `.venv310` priorität, Fallback `.venv` |
| Env-Vars beim Start | `start_pb_studio.py:85-90` | `VIRTUAL_ENV`, `CUDA_MODULE_LOADING=LAZY` |
| PyInstaller-Spec | `pb_studio.spec:1-120+` | Entry `main.py`, `collect_all()` für PySide6/torch, 120+ hidden imports |
| Test-Fixtures | `tests/conftest.py:25-137` | In-Memory SQLite mit `check_same_thread=False`, FK-Enforcement |
| Worker-Patching | `tests/conftest.py:51-60` | `nullpool_session()` |
| Service-Patching | `tests/conftest.py:63-79` | 6 Service-Module patchbar |

---

## 2. Technologie-Entscheidungen

### 2.1 Frontend-Bibliothek: vis-network 9.1.x (MVP)

| Kriterium | vis-network 9.1.x | Cytoscape.js 3.x | Sigma.js 2.x |
|---|---|---|---|
| Rendering | Canvas | Canvas | **WebGL** |
| Performance 100 Knoten | sehr gut | sehr gut | sehr gut |
| Performance 1.000 Knoten | gut | gut | sehr gut |
| Performance 5.000 Knoten | **knapp** (ruckelt) | gut | sehr gut |
| Physics out-of-box | ja (Barnes-Hut) | ja (Cola, Elk) | manuell |
| API-Einstiegshürde | niedrig | mittel | hoch |
| Bundle-Größe | ~250 KB | ~450 KB | ~150 KB (ohne Layouts) |
| Community / Pflege | aktiv (visjs.github.io) | sehr aktiv | aktiv |
| Events/Clustering | eingebaut | eingebaut | manuell |

**Entscheidung:**
- **MVP (bis 1.000 Knoten):** vis-network 9.1.19 (oder neueste 9.1.x zum Zeitpunkt von Phase 1.1).
- **Upgrade-Pfad bei >2.000 Knoten:** Cytoscape.js (gleiches Datenformat, gleiche QWebChannel-Bridge, Austausch primär in der HTML-Datei).
- **Sigma.js nur wenn Cytoscape.js nicht ausreicht:** erfordert Neuschreiben der Layout-Logik.

### 2.2 Graph-Bibliothek: NetworkX 3.6.x

Bereits in `requirements.txt:52` gepinnt für Python 3.11+. Für `.venv310` separat installieren (pure Python, keine C-Abhängigkeiten, trivial).

**Alternativen nicht gewählt:**
- `igraph` (C-Binary, ~10 MB Mehraufwand, nur bei >5.000 Knoten relevant)
- `graph-tool` (Linux-only build)

### 2.3 ANN-Bibliothek: keine im MVP

Für 100–2.000 Clips reicht Brute-Force `numpy` Cosine-Similarity (Matmul + argpartition). Bei 5.000 Clips: ~200–400 ms auf CPU, akzeptabel.

**Upgrade-Pfad bei >5.000 Clips:** `usearch` (pure Python, pip-install, kompakter als faiss).

### 2.4 Persistenz: keine im MVP

Graph in-memory, bei Projekt-Load neu berechnet (<500 ms für 1.000 Clips). Erst wenn das Aufbauen spürbar wird, Persistenz nachrüsten.

**Begründung:** Cache-Invalidierung ist Fehlerquelle; Neuaufbau ist deterministisch und schnell.

---

## 3. Risiko-Matrix (erweitert)

| # | Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation | Phase |
|---|---|---|---|---|---|
| R-1 | **PyInstaller + QtWebEngine Windows-Bundling** (fehlendes QtWebEngineProcess.exe, Chromium-Locales, Antivirus-Quarantäne) | HOCH | KRITISCH | Frühzeitig Spike S3 in Phase 0; manuelle `.spec`-Erweiterung mit `collect_all('PySide6.QtWebEngineCore')` + explizite `datas` für `translations/qtwebengine_locales/` und `resources/`. Notfall: Windows-Code-Signing. | 0, 5 |
| R-2 | vis-network Performance bei >2.000 Knoten | MITTEL | MITTEL | Upgrade-Pfad zu Cytoscape.js vorbereitet. Auto-Clustering ab 50 Knoten in vis.js-Config. | 1, 2 |
| R-3 | RAM-Druck Chromium + SigLIP + Demucs + Gemma gleichzeitig | MITTEL | MITTEL | QWebEngine nutzt System-RAM (~400–800 MB), nicht VRAM. Kein Konflikt mit GPU-Modellen, aber auf 16-GB-Systemen knapp. Monitoring-Setting im Settings-Store. | 5 |
| R-4 | QWebChannel-Bridge verliert Events bei hoher Frequenz | NIEDRIG | MITTEL | Debouncing auf JS-Seite, Batch-Signals Python-seitig. Spike S2 verifiziert. | 0, 2 |
| R-5 | Thread-Deadlock zwischen Graph-Build und UI | MITTEL | HOCH | Graph-Build immer in `QThread`, niemals direkt im Main-Thread. Lock-Reihenfolge dokumentieren. | 1 |
| R-6 | Windows SmartScreen/Defender auf unsigniertem Chromium-Bundle | MITTEL | NIEDRIG | Kein Fix, nur User-Kommunikation im Installer („Beim ersten Start bitte bestätigen"). | 5 |
| R-7 | Versions-Drift zwischen `requirements.txt` (3.11+) und `.venv310` (3.10) | HOCH | NIEDRIG | Eigene Graph-Dependencies nur auf 3.10 testen. `requirements.txt` nicht ändern (separates Problem). | 0 |
| R-8 | vis-network CPU-Last im Physics-Solver blockiert App | MITTEL | MITTEL | `stabilization.iterations: 150` hart begrenzen, `smooth: false` für Edges, Physics nach Stabilisierung auto-deaktivieren. | 2 |
| R-9 | Ollama-Strategist-Konflikt (keiner) — Graph-System ist read-only auf Ollama-Outputs | NIEDRIG | KEINE | Keine Integration nötig. | — |

---

## 4. Phase 0 — Spike / Go-No-Go (2 Arbeitstage)

**Ziel:** Vier isolierte Wegwerf-Skripte in `scripts/spikes/` beweisen oder widerlegen die vier killerfähigen Annahmen. Kein Integrationscode, keine Änderung an `services/` oder `ui/`.

**Abbruch-Kriterium für das gesamte Projekt:** Wenn S1 oder S3 scheitert, wird der Plan nicht weiter verfolgt. Fallback-Pfad (QGraphicsView-Native) ist zu teuer (+15 Tage) und wird nur bei klarer Business-Entscheidung aktiviert.

### Aufgabe 0.1 — Verzeichnis & Basis-Setup (30 min)

- **Input:** CWD = PB Studio Root
- **Aktionen:**
  1. Verzeichnis anlegen: `scripts/spikes/graph/`
  2. `scripts/spikes/graph/README.md` mit Kurzbeschreibung der vier Spikes
  3. `scripts/spikes/graph/requirements_spike.txt`: `networkx==3.3` (3.10-kompatible Version)
  4. In `.venv310` installieren: `.venv310/Scripts/pip.exe install networkx==3.3`
- **Akzeptanz:** `.venv310/Scripts/python.exe -c "import networkx; print(networkx.__version__)"` gibt `3.3` aus.
- **Risiko:** Keins.

### Aufgabe 0.2 — Spike S1: vis.js in QWebEngineView (3–4 h)

- **Datei:** `scripts/spikes/graph/s1_webengine_visjs.py` (Python, ca. 60 Zeilen)
- **Ressourcen:**
  - `scripts/spikes/graph/resources/vis-network.min.js` (~250 KB, herunterladen von `https://unpkg.com/vis-network@9.1.19/standalone/umd/vis-network.min.js`)
  - `scripts/spikes/graph/resources/vis-network.min.css` (~30 KB, `https://unpkg.com/vis-network@9.1.19/dist/dist/vis-network.min.css`)
  - `scripts/spikes/graph/resources/graph_viewer_s1.html` — minimalistische HTML mit 50 Dummy-Knoten
- **Aktionen:**
  1. `QApplication` + `QMainWindow` + `QWebEngineView` aufbauen
  2. HTML-Datei lokal laden (`QUrl.fromLocalFile()`)
  3. HTML rendert 50 Knoten mit Barnes-Hut-Physics, `stabilization.iterations: 150`
  4. Zoom-Verhalten prüfen, Drag prüfen, kein White-Screen
- **Akzeptanz:**
  - Window öffnet binnen <2 s
  - Graph erscheint, Physics stabilisiert sich in <3 s
  - Kein Console-Error im Qt-Log
  - Maus-Zoom und Drag funktionieren
- **Widerlegt wenn:** WebEngine crasht, vis.js wirft Fehler, keine Render-Ausgabe.
- **Dauer:** 3–4 h
- **Kritikalität:** HOCH (killt Projekt bei Scheitern)

### Aufgabe 0.3 — Spike S2: QWebChannel JS↔Python Bridge (2–3 h)

- **Datei:** `scripts/spikes/graph/s2_webchannel_bridge.py` (erweitert S1)
- **Zusätzliche Ressource:** `scripts/spikes/graph/resources/qwebchannel.js` (Kopie aus Qt-Installation oder von `qrc:///qtwebchannel/qwebchannel.js` referenzieren)
- **Aktionen:**
  1. `QObject`-Subklasse `SpikeBridge` mit einem `@Slot(str)` namens `on_node_click` und einem `Signal(str)` namens `node_updated`
  2. `QWebChannel` registrieren, Bridge-Objekt per `channel.registerObject("bridge", ...)` einhängen
  3. HTML erweitern: QWebChannel-Setup im `<script>`-Block, Button der `bridge.on_node_click('test-node-42')` aufruft
  4. Python-Log-Output pro Empfang
  5. Stress-Test: 100 Klicks per `setInterval(10ms)` — alle müssen ankommen
- **Akzeptanz:**
  - 100/100 Events kommen in Python an
  - Keine verlorenen Events, keine Deadlocks
  - Python→JS-Richtung: `web_view.page().runJavaScript(...)` führt JS-Funktion aus
- **Widerlegt wenn:** Events droppen (>1 %), Deadlock, Bridge-Objekt nicht erreichbar aus JS.
- **Dauer:** 2–3 h
- **Kritikalität:** HOCH

### Aufgabe 0.4 — Spike S3: PyInstaller-Bundle auf sauberem Windows (4–6 h)

- **Datei:** `scripts/spikes/graph/s3_pyinstaller_test.spec`
- **Aktionen:**
  1. Minimal-.spec-Datei, die nur S1+S2-Skript und die drei HTML/JS/CSS-Ressourcen bundelt
  2. `collect_all('PySide6')` + explizite `collect_data_files('PySide6', subdir='plugins/webengine')` + `collect_data_files('PySide6', subdir='translations/qtwebengine_locales')`
  3. `hiddenimports = ['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebChannel']`
  4. Build: `.venv310/Scripts/pyinstaller.exe scripts/spikes/graph/s3_pyinstaller_test.spec --distpath scripts/spikes/graph/dist --workpath scripts/spikes/graph/build --clean`
  5. Ergebnis (`dist/s3_pyinstaller_test/s3_pyinstaller_test.exe`) auf **sauberem Windows 11** oder in VirtualBox/Hyper-V-VM ohne Python testen
- **Akzeptanz:**
  - App startet binnen <5 s auf sauberem Windows
  - vis.js rendert
  - QWebChannel funktioniert (S2-Stress-Test grün)
  - Kein SmartScreen-Block (darf Warnung zeigen, User kann bestätigen)
- **Widerlegt wenn:**
  - `QtWebEngineProcess.exe` fehlt oder crasht
  - Chromium startet nicht (fehlende Locales, resources)
  - App startet, aber Render bleibt weiß
- **Dauer:** 4–6 h (davon 1–2 h Debugging-Puffer für Windows-Pfad-Issues)
- **Kritikalität:** KRITISCH (häufigster Abbruch-Grund)

### Aufgabe 0.5 — Spike S4: Performance-Test 1152-dim (1–2 h)

- **Datei:** `scripts/spikes/graph/s4_performance_test.py`
- **Aktionen:**
  1. Generiere `np.random.randn(N, 1152).astype(np.float32)` für N ∈ {100, 500, 1.000, 2.000, 5.000}
  2. L2-Normalisiere Zeilen
  3. Messe: `matmul` (M @ M.T), `argpartition` Top-20 pro Zeile, Edge-List-Aufbau
  4. Optional: SigLIP-Modell laden (aus ModelManager), 200 MB VRAM belegen, danach einen dummy `QWebEngineView` öffnen — Stabilitätstest
  5. CSV-Ausgabe: `(n, matmul_ms, argpartition_ms, edges_ms, total_ms, peak_ram_mb)`
- **Akzeptanz:**
  - 1.000 Clips: total <500 ms
  - 5.000 Clips: total <2.000 ms
  - 5.000 Clips: Peak-RAM <500 MB
  - WebEngine + SigLIP gleichzeitig: kein OOM
- **Widerlegt wenn:** 5.000 Clips >3 s, oder RAM-Spike >2 GB, oder OOM beim Parallel-Test.
- **Dauer:** 1–2 h
- **Kritikalität:** NIEDRIG (würde nur Skalierungs-Grenze setzen)

### Aufgabe 0.6 — Go/No-Go-Entscheidung (30 min)

- **Input:** Ergebnisse S1–S4
- **Aktionen:**
  1. Kurze Markdown-Datei `scripts/spikes/graph/SPIKE_RESULTS.md` schreiben mit je Spike: pass/fail + Messdaten
  2. Entscheidung dokumentieren:
     - **Alle vier grün:** GO für Phase 1
     - **S1, S2, S4 grün; S3 gelb mit Workaround:** GO mit Einschränkung — PyInstaller-Aufwand in Phase 5 erhöht
     - **S1 oder S3 rot:** NO-GO. Projekt abbrechen oder auf QGraphicsView-Native umplanen (separate Entscheidung).
- **Akzeptanz:** Klare schriftliche Entscheidung mit Begründung.
- **Kritikalität:** GATE.

---

## 5. Phase 1 — MVP (8–10 Arbeitstage)

**Scope:** Minimales funktionierendes Graph-System, das (a) eine visuelle Karte der Video-Clips zeigt und (b) Clip-Wiederholungen im Auto-Edit verhindert. Keine Beat-/Audio-/Section-Knoten, keine komplexe Reward-Funktion, keine Persistenz.

**Abgrenzung:** Alles außerhalb dieser Scope-Liste ist Phase 2.

### Sprint 1.1 — Graph-Engine Kern (Tag 1–3)

#### Aufgabe 1.1.1 — Abhängigkeits-Setup (30 min)

- **Input:** Go-Entscheidung aus 0.6
- **Aktionen:**
  1. `.venv310/Scripts/pip.exe install networkx==3.3` (sofern nicht bereits durch Phase 0 erfolgt)
  2. `requirements_310.txt` (falls existent) oder eigenes `requirements_graph.txt` in Root mit allen neuen Zeilen anlegen
  3. Notiz in `docs/PHASE4_COMPLETION_REPORT.md`-Nachfolger oder neuer Datei `docs/graph_system_dependencies.md`
- **Dateien neu:** `requirements_graph.txt`, `docs/graph_system_dependencies.md`
- **Akzeptanz:** `python -c "import networkx as nx; print(nx.__version__)"` läuft.
- **Dauer:** 30 min

#### Aufgabe 1.1.2 — GraphService Skelett (2 h)

- **Datei neu:** `services/graph_service.py`
- **Struktur (leer zu implementieren):**
  - Modul-Docstring: Zweck, Singleton-Referenz auf `vector_db_service.py`
  - Imports: `networkx as nx`, `numpy as np`, `threading`, `logging`, `pathlib.Path`, `typing`
  - Konstanten:
    - `DEFAULT_K = 20`
    - `DEFAULT_THRESHOLD = 0.3`
    - `MAX_BRUTE_FORCE_NODES = 5000`
  - Klasse `GraphService` mit `__new__()` Singleton + `_instance_lock`
  - Privates: `_graph: Optional[nx.Graph]`, `_lock: threading.Lock()`, `_last_build_ms: float`
  - Public-Skeleton-Methoden (nur `pass`, Signaturen fixieren):
    - `build_video_similarity_graph(k: int = DEFAULT_K, threshold: float = DEFAULT_THRESHOLD) -> nx.Graph`
    - `get_graph() -> Optional[nx.Graph]`
    - `get_graph_distance(node_a: str, node_b: str) -> int` (returnt `sys.maxsize` bei kein Pfad)
    - `get_vis_js_data() -> dict`
    - `reset() -> None`
  - Factory `get_graph_service() -> GraphService` analog anderen Services
- **Input:** keine
- **Output:** funktionierendes Import, Singleton-Identität zweier Aufrufe identisch
- **Akzeptanz:** Unit-Test `test_graph_service_singleton.py`: zwei Aufrufe geben dieselbe Instanz, Thread-Test mit 10 parallelen `get_graph_service()` liefert immer dieselbe Instanz.
- **Dauer:** 2 h

#### Aufgabe 1.1.3 — k-NN-Berechnung implementieren (3 h)

- **Datei:** `services/graph_service.py` (neue private Methode)
- **Methode:** `_compute_knn_edges(embeddings: np.ndarray, metadata: list[dict], k: int, threshold: float) -> list[tuple[str, str, float]]`
- **Algorithmus:**
  1. Validierung: wenn `len(embeddings) == 0`, return `[]`
  2. L2-Normalisierung: `norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8; X = embeddings / norms`
  3. Brute-Force-Pfad (wenn `N <= MAX_BRUTE_FORCE_NODES`):
     - `sim = X @ X.T`
     - Setze Diagonale auf `-np.inf` (Selbst-Ähnlichkeit nicht in k-NN)
     - Für jede Zeile `i`: `top_k = np.argpartition(-sim[i], k)[:k]`
     - Für jedes `j` in `top_k`: wenn `sim[i, j] > threshold`, dann `edges.append((metadata[i]['node_id'], metadata[j]['node_id'], float(sim[i, j])))`
  4. Dedup: (a,b) und (b,a) auf kanonische Form (kleinere ID zuerst), mit max-Score-Reduktion
  5. Return edges
- **Akzeptanz:**
  - Unit-Test mit 100 random Embeddings 1152-dim: liefert ≤2000 kanten
  - Test `test_knn_symmetry`: keine Duplikate (a,b) + (b,a)
  - Test `test_knn_threshold`: alle edges haben weight > 0.3
  - Test `test_knn_self_loops`: keine Kante a↔a
  - Performance: 1.000 Knoten <300 ms auf `.venv310` Entwickler-Maschine
- **Dauer:** 3 h

#### Aufgabe 1.1.4 — Node-ID-Konventionen & Datenzugriff (2 h)

- **Datei:** `services/graph_service.py` (neue private Methode)
- **Methode:** `_load_video_clip_nodes() -> tuple[np.ndarray, list[dict]]`
- **Algorithmus:**
  1. Import `from services.vector_db_service import get_vector_db_service` (nutzt bestehenden Factory-Aufruf, siehe `vector_db_service.py`)
  2. Rufe `vector_db.get_all_embeddings()` auf (returnt `(matrix, metadata_list)`)
  3. Konstruiere für jedes Metadata-Item ein Dict mit:
     - `node_id`: `f"v_{scene_id}"` (Scene.id aus der Haupt-DB, nicht clip_embeddings.id)
     - `type`: `"video_clip"`
     - `video_path`, `scene_index`, `scene_start`, `scene_end`, `motion_score`, `description`
  4. Cross-Reference: metadata aus `clip_embeddings` hat `video_path` + `scene_index` — per SQL-Query gegen `scenes`-Tabelle die `Scene.id` holen (Join über `VideoClip.file_path == clip_embeddings.video_path` + Scene.start_time ~ scene_start)
  5. Return `(matrix, enriched_metadata)`
- **Akzeptanz:**
  - Test mit 3 VideoClips mit je 2 Scenes: Rückgabe hat 6 Einträge, alle node_ids unique
  - Test mit leerer DB: Rückgabe `(np.array([]).reshape(0, 1152), [])`
- **Risiko-Anmerkung:** Join-Logik ist fehleranfällig wenn `video_path` normalisierungs-inkonsistent ist. Eventuell Hilfs-Helper aus `services/ingest_service.py` wiederverwenden.
- **Dauer:** 2 h

#### Aufgabe 1.1.5 — build_video_similarity_graph() implementieren (1.5 h)

- **Datei:** `services/graph_service.py`
- **Methode:** `build_video_similarity_graph(k=20, threshold=0.3) -> nx.Graph`
- **Algorithmus:**
  1. Acquire `self._lock`
  2. Start-Timer
  3. `embeddings, metadata = self._load_video_clip_nodes()`
  4. `G = nx.Graph()`
  5. Alle Knoten hinzufügen: `G.add_node(m['node_id'], **m)` für jedes m
  6. Edges berechnen: `edges = self._compute_knn_edges(embeddings, metadata, k, threshold)`
  7. `G.add_weighted_edges_from(edges)` (Format: `(u, v, w)`)
  8. End-Timer → `self._last_build_ms`
  9. `self._graph = G`
  10. Release Lock, return G
- **Akzeptanz:**
  - Integration-Test mit Fixture-DB (20 VideoClips mit echten Scene-Einträgen und Dummy-Embeddings): Graph hat 20 Knoten, Kanten > 0, `_last_build_ms > 0`.
  - Test `test_build_empty_db`: Graph hat 0 Knoten.
  - Test `test_build_single_clip`: 1 Knoten, 0 Kanten.
- **Dauer:** 1.5 h

#### Aufgabe 1.1.6 — get_vis_js_data() implementieren (1.5 h)

- **Datei:** `services/graph_service.py`
- **Methode:** `get_vis_js_data() -> dict`
- **Algorithmus:**
  1. Wenn `self._graph is None`, return `{"nodes": [], "edges": []}`
  2. `nodes = [{"id": n, "label": data.get("scene_index", n), "group": "video_clip", "title": data.get("description", "")[:200]} for n, data in self._graph.nodes(data=True)]`
  3. `edges = [{"from": u, "to": v, "value": d["weight"]} for u, v, d in self._graph.edges(data=True)]`
  4. Return `{"nodes": nodes, "edges": edges}`
- **Akzeptanz:**
  - Test: Output ist JSON-serialisierbar (`json.dumps(...)` ohne Fehler)
  - Test: Anzahl nodes == `G.number_of_nodes()`, anzahl edges == `G.number_of_edges()`
- **Dauer:** 1.5 h

#### Aufgabe 1.1.7 — get_graph_distance() implementieren (1 h)

- **Datei:** `services/graph_service.py`
- **Methode:** `get_graph_distance(node_a: str, node_b: str) -> int`
- **Algorithmus:**
  1. Wenn Graph leer oder eines der Knoten nicht vorhanden: return `sys.maxsize`
  2. `try: return nx.shortest_path_length(self._graph, node_a, node_b)`
  3. `except nx.NetworkXNoPath: return sys.maxsize`
  4. `except nx.NodeNotFound: return sys.maxsize`
- **Akzeptanz:**
  - Test auf 5-Knoten-Kette (A-B-C-D-E): distance(A, E) == 4, distance(A, A) == 0, distance(A, "nonexistent") == maxsize
- **Dauer:** 1 h

#### Aufgabe 1.1.8 — Singleton-Reset in session.py (30 min)

- **Datei:** `database/session.py`
- **Aktion:** In `_patch_service_paths()` (`session.py:283-303`) nach dem VectorDB-Reset einen Reset für GraphService ergänzen:
  ```
  from services.graph_service import GraphService
  GraphService._instance = None
  ```
  (Exakte Zeile vorher verifizieren; einfügen im gleichen Stil wie vorhandene Service-Resets.)
- **Akzeptanz:**
  - Integrations-Test: Projekt A → Graph bauen → Projekt B laden → `get_graph_service()` gibt neue Instanz, `get_graph()` ist None.
- **Dauer:** 30 min

#### Aufgabe 1.1.9 — Unit-Test-Suite für GraphService (2 h)

- **Datei neu:** `tests/services/test_graph_service.py`
- **Tests:**
  - `test_singleton_identity`
  - `test_singleton_thread_safety` (10 Threads parallel)
  - `test_build_empty_db` (leere DB-Fixture)
  - `test_build_single_clip`
  - `test_build_100_clips_synthetic_embeddings`
  - `test_knn_no_self_loops`
  - `test_knn_symmetry_dedup`
  - `test_knn_threshold_filter`
  - `test_vis_js_export_schema` (JSON-serialisierbar, erwartete Keys)
  - `test_graph_distance_basic`
  - `test_graph_distance_no_path`
  - `test_graph_distance_unknown_node`
  - `test_singleton_reset_on_project_switch` (Integration mit session.py)
- **Fixtures:** nutzt `conftest.py`-Patterns (`test_engine`, `db_session`, plus Hilfs-Fixture für Fake-Embeddings)
- **Akzeptanz:** Alle Tests grün; Coverage `services/graph_service.py` ≥ 80 %.
- **Dauer:** 2 h

### Sprint 1.2 — UI-Panel & vis.js (Tag 4–6)

#### Aufgabe 1.2.1 — HTML-Frontend (2 h)

- **Dateien neu:**
  - `resources/graph/graph_viewer.html`
  - `resources/graph/vis-network.min.js` (Download 9.1.19 aus unpkg, ~250 KB)
  - `resources/graph/vis-network.min.css` (~30 KB)
  - `resources/graph/qwebchannel.js` (Kopie aus `PySide6/Qt6/resources/` oder Qt-Ressource referenzieren)
- **HTML-Struktur:**
  - `<head>`: Meta-Tags, CSS-Link, Script-Tags für vis-network.min.js + qwebchannel.js
  - `<body>`: `<div id="graph-container" style="width:100vw; height:100vh;"></div>`
  - `<script>`: QWebChannel-Setup, vis.js Network-Instantiierung, globale Funktionen `updateGraph(data)`, `highlightNode(id)`, `filterEdges(minWeight)`
- **vis.js-Config** (wie Studie Teil C Schritt 2.1, aber ohne `beat`/`audio_segment`/`music_section` Gruppen im MVP):
  - Physics: Barnes-Hut, `stabilization.iterations: 150`, `updateInterval: 25`
  - Edges: `smooth: false`, `color.inherit: 'both'`, `width: 0.5`
  - Groups: nur `video_clip`-Gruppe mit Farbe `#4FC3F7`, Form `dot`
  - Interaction: `hover: true`, `tooltipDelay: 200`, `navigationButtons: true`
- **JS-Funktionen (MVP):**
  - `updateGraph(data)`: setzt neue DataSet(nodes) + DataSet(edges), physics-stabilisierung läuft
  - `highlightNode(id)`: zoomt auf Knoten, setzt selection
  - `filterEdges(minWeight)`: updatet edges-dataset mit gefilterter Liste
  - Event-Handler: `network.on('click', (params) => { if (params.nodes.length > 0) bridge.on_node_clicked(params.nodes[0]); })`
  - Event-Handler: `network.on('doubleClick', ...)` analog mit `bridge.on_node_double_clicked(...)`
- **Akzeptanz:** Statisch in S1-Spike-Setup lädt und rendert.
- **Dauer:** 2 h

#### Aufgabe 1.2.2 — GraphBridge implementieren (2 h)

- **Datei neu:** `services/graph_bridge.py`
- **Klasse:** `GraphBridge(QObject)`
- **Signals:**
  - `node_clicked = Signal(str)`
  - `node_double_clicked = Signal(str)`
  - `selection_changed = Signal(list)`
- **Slots (JS → Python):**
  - `@Slot(str) on_node_clicked(self, node_id: str)` — loggt, emittiert `self.node_clicked`
  - `@Slot(str) on_node_double_clicked(self, node_id: str)`
  - `@Slot("QVariantList") on_selection_changed(self, node_ids: list)`
- **Python → JS Methoden (keine Slots, normale Python-Methoden):**
  - `push_graph_data(self)`: holt `GraphService().get_vis_js_data()`, ruft `self._web_view.page().runJavaScript(f"updateGraph({json.dumps(data)})")`
  - `highlight_node(self, node_id: str)`: `runJavaScript(f"highlightNode('{node_id}')")`
  - `set_edge_threshold(self, min_weight: float)`: `runJavaScript(f"filterEdges({min_weight})")`
- **Attribute:** `self._web_view: QWebEngineView` (wird von GraphPanel gesetzt)
- **Akzeptanz:**
  - Unit-Test `test_bridge_signals.py`: Slot-Aufruf emittiert Signal (`pytest-qt` Fixture `qtbot`)
- **Dauer:** 2 h

#### Aufgabe 1.2.3 — GraphPanel Widget implementieren (3 h)

- **Datei neu:** `ui/panels/graph_panel.py`
- **Klasse:** `GraphPanel(QWidget)`
- **Struktur:**
  - `__init__(self, parent=None)`:
    - Super-Call
    - `self.web_view = QWebEngineView(self)`
    - `self.channel = QWebChannel(self.web_view.page())`
    - `self.bridge = GraphBridge()`
    - `self.bridge._web_view = self.web_view`
    - `self.channel.registerObject("bridge", self.bridge)`
    - `self.web_view.page().setWebChannel(self.channel)`
    - HTML laden: `html_path = Path(__file__).resolve().parent.parent.parent / "resources" / "graph" / "graph_viewer.html"`; `self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))`
    - Layout: `QVBoxLayout`, `setContentsMargins(0,0,0,0)`, Toolbar oben, WebView darunter
  - `_build_toolbar()`: Methode erzeugt `QToolBar` mit Buttons:
    - „Graph aufbauen" → `self._rebuild_graph()`
    - „Zoom Fit" → `self.bridge.highlight_node("")` (Leere ID = fit)
    - „Threshold"-Slider (0.0–1.0, Default 0.3) → `self.bridge.set_edge_threshold(value)`
    - Optional: Status-Label „N Knoten, M Kanten, T ms"
  - `_rebuild_graph(self)`:
    - `QThread`-basiert (oder `QRunnable` + `QThreadPool`) — **nicht im Main-Thread**
    - Thread ruft `GraphService().build_video_similarity_graph()`
    - Fertig-Signal → `self.bridge.push_graph_data()` + Status-Label update
    - Progress-Anzeige (QProgressBar oder Statusleiste)
  - `closeEvent()`: Cleanup-Hook
- **Akzeptanz:** Manuell im laufenden PB Studio: Panel öffnet, Button „Graph aufbauen" startet Thread, Render erscheint.
- **Dauer:** 3 h

#### Aufgabe 1.2.4 — Dock-Einhängung in PBWindow (1 h)

- **Datei:** `main.py` (an passender Stelle in `PBWindow.__init__`, nach Zeile 274, analog zu bestehendem Chat-Dock-Pattern)
- **Alternative Datei:** `ui/controllers/panel_setup.py` (neue Methode `setup_graph_dock()` analog zu `setup_chat_dock()`, Zeile 70-127)
- **Aktion:**
  1. Import: `from ui.panels.graph_panel import GraphPanel`
  2. Erzeugen: `self.graph_dock = QDockWidget("Graph", self)`
  3. `self.graph_panel = GraphPanel(self.graph_dock)`
  4. `self.graph_dock.setWidget(self.graph_panel)`
  5. `self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.graph_dock)` (oder Right, je nach Platz)
  6. Default: `self.graph_dock.hide()` — via Menüpunkt aktivierbar
  7. Menu-Eintrag unter „View" → „Graph-Panel anzeigen" mit Checkbox
- **Akzeptanz:** Nach App-Start zeigt Menu den Eintrag; Klick toggled Dock.
- **Dauer:** 1 h

#### Aufgabe 1.2.5 — Klick-Interaktion: Knoten → Preview (2 h)

- **Datei:** `ui/panels/graph_panel.py` + Verbindung zu Preview-System
- **Aktion:**
  1. Im `GraphPanel.__init__`: `self.bridge.node_clicked.connect(self._on_node_clicked)`
  2. `_on_node_clicked(self, node_id: str)`:
     - Parse: `scene_id = int(node_id.removeprefix("v_"))`
     - Hole Scene aus DB (über `database.session` + `Scene`-Query)
     - Signal emittieren: `self.scene_selected = Signal(int)` — `self.scene_selected.emit(scene_id)`
  3. In `PBWindow` oder `EditWorkspace`: `graph_panel.scene_selected.connect(self._preview_scene)` (Existierender Preview-Mechanismus verwenden)
- **Akzeptanz:** Klick auf Knoten im Graph startet Video-Preview des entsprechenden Scenes.
- **Dauer:** 2 h

### Sprint 1.3 — Pacing-Integration: Anti-Repetition (Tag 7–8)

#### Aufgabe 1.3.1 — Anti-Repetition-Filter implementieren (2 h)

- **Datei neu:** `services/graph_pacing_integration.py`
- **Funktion:** `is_repetition_safe(clip_id_a: int, clip_id_b: int, min_distance: int = 2) -> bool`
- **Algorithmus:**
  1. `graph_service = get_graph_service()`
  2. Wenn `graph_service.get_graph() is None`: return `True` (kein Graph = kein Constraint)
  3. `node_a = f"v_{clip_id_a}"; node_b = f"v_{clip_id_b}"`
  4. `distance = graph_service.get_graph_distance(node_a, node_b)`
  5. return `distance >= min_distance`
- **Akzeptanz:**
  - Unit-Tests: keine Pfade → True; direkte Nachbarn (distance=1) → False bei min_distance=2; distance=3 → True
- **Dauer:** 2 h

#### Aufgabe 1.3.2 — Integration in _match_video_for_segment (3 h)

- **Datei:** `services/pacing_edit_helpers.py`
- **Ort:** Nach Zeile 962 (bestehender `used_recently`-Filter)
- **Aktion:**
  1. Neuer Parameter in Signatur `_match_video_for_segment()`: `use_graph_diversity: bool = True`, `graph_min_distance: int = 2`, `prev_clip_db_id: Optional[int] = None`
  2. Nach dem `used_recently`-Filter: zusätzlichen Filter einfügen:
     ```
     if use_graph_diversity and prev_clip_db_id is not None:
         from services.graph_pacing_integration import is_repetition_safe
         candidates = [c for c in candidates
                       if is_repetition_safe(prev_clip_db_id, c["clip_db_id"], graph_min_distance)]
     ```
  3. Fallback: wenn nach Filter `len(candidates) == 0`, dann Filter ignorieren (kein Block durch Graph)
- **Aufrufer anpassen:** Alle Aufrufer von `_match_video_for_segment` (grep im Repo) müssen den neuen Parameter `prev_clip_db_id` durchreichen. Prev-Clip wird aus dem letzten erfolgreich gematchten Segment in der Schleife im `auto_edit_phase3`-Aufrufer getrackt.
- **Akzeptanz:**
  - Bestehende Pacing-Tests laufen weiter grün (Regression)
  - Neuer Test: Pacing mit 10 identischen Clips (alle Nachbarn im Graph) + min_distance=2 → Pacing nutzt Fallback, keine Crash
  - Neuer Test: Pacing mit diversen Clips → konsekutive Clips haben Graph-Distanz >= 2
- **Dauer:** 3 h

#### Aufgabe 1.3.3 — AdvancedPacingSettings erweitern (1 h)

- **Datei:** `services/pacing_beat_grid.py:115-126`
- **Aktion:** Neue Felder in `AdvancedPacingSettings`-dataclass:
  ```
  use_graph_diversity: bool = False   # Feature-Flag, Default aus
  graph_min_distance: int = 2
  ```
- **Default = False:** Damit MVP keinen Regression-Einfluss auf bestehendes Verhalten hat, solange Feature nicht aktiv.
- **Settings-Store:** `services/settings_store.py` (falls vorhanden) erweitern um `graph`-Subsektion; alternativ Settings-Dict direkt in PacingWorkspace.
- **Akzeptanz:** Dataclass instantiierbar, defaults korrekt, Test `test_settings_roundtrip`.
- **Dauer:** 1 h

#### Aufgabe 1.3.4 — Settings-UI-Toggle (1.5 h)

- **Datei:** `ui/workspaces/edit_workspace.py` (oder der Dialog der `AdvancedPacingSettings` darstellt)
- **Aktion:** Checkbox „Anti-Wiederholung (Graph)" + Spinner für `min_distance` (1–5). Signalkette: Checkbox → Settings-Update → nächster Pacing-Run nutzt Wert.
- **Akzeptanz:** UI-Test: Toggle speichert, Pacing berücksichtigt Einstellung.
- **Dauer:** 1.5 h

### Sprint 1.4 — MVP-Abschluss (Tag 9–10)

#### Aufgabe 1.4.1 — Integrations-Test-Suite (3 h)

- **Datei neu:** `tests/integration/test_graph_full_flow.py`
- **Tests:**
  - `test_full_graph_build_20_clips`: 20 Scenes via Fixture, Graph gebaut, Panel öffnet, vis.js rendert (headless über `pytest-qt` möglich? sonst skippen in CI)
  - `test_anti_repetition_blocks_duplicate`: Pacing mit 5 Clips + 5 identischen Kopien, Graph mit k=2 → Pacing-Output enthält keine konsekutiven Kopien
  - `test_project_switch_resets_graph`: Projekt A build → Projekt B laden → Graph ist None → neu bauen
  - `test_empty_project`: Kein Crash, leeres Panel-Rendering
- **Dauer:** 3 h

#### Aufgabe 1.4.2 — Logging & Error-Handling-Review (2 h)

- **Datei:** `services/graph_service.py`, `services/graph_bridge.py`, `services/graph_pacing_integration.py`, `ui/panels/graph_panel.py`
- **Aktion:**
  1. `logging.getLogger(__name__)` in jedem Modul
  2. Log-Levels: INFO (Build-Start, Build-Ende mit `n_nodes`, `n_edges`, `ms`), WARNING (leerer Graph, Node nicht gefunden), ERROR (Thread-Crash, JSON-Serialization-Fehler)
  3. Try/Except um jeden I/O- und JS-Call in Bridge
  4. QWebEngineView: `loadFinished`-Signal abfragen, bei Fehler Log
- **Akzeptanz:** Code-Review-Checklist abgearbeitet.
- **Dauer:** 2 h

#### Aufgabe 1.4.3 — Dokumentation (2 h)

- **Datei neu:** `docs/graph_system_user_guide.md`
- **Inhalt:**
  - Kurz: was macht das Graph-Panel
  - Menu: „View → Graph-Panel"
  - Toolbar-Buttons Erklärung
  - Bekannte Grenzen (MVP: nur Video-Video-Kanten, keine Beat-Integration)
  - Settings-Toggle „Anti-Wiederholung"
- **Datei neu:** `docs/graph_system_developer_guide.md`
- **Inhalt:**
  - Architektur: GraphService, GraphBridge, GraphPanel
  - Erweiterungspunkte: Knoten-Typen hinzufügen, Kanten-Typen hinzufügen, Reward-Funktion
  - Testing-Conventions
  - Troubleshooting: Chromium-DevTools öffnen, Threading-Issues
- **Dauer:** 2 h

#### Aufgabe 1.4.4 — Manueller End-to-End-Rauchtest (1 h)

- **Aktion:**
  1. Echtes Projekt mit ~30 Scenes laden
  2. Graph aufbauen (<1 s)
  3. Zoom-/Drag-Interaktion prüfen
  4. Klick auf Knoten → Video-Preview
  5. Anti-Repetition-Toggle: Pacing vorher/nachher vergleichen (Repetition-Rate in beiden Runs messen)
- **Akzeptanz:** Alle Schritte funktionieren, kein Crash, keine Einfrierer.
- **Dauer:** 1 h

---

## 6. Phase 2 — Vollausbau (10–14 Tage, optional)

**Trigger:** Nur nach positivem User-Feedback auf MVP. Nicht automatisch Teil dieses Plans.

Aufgabenblöcke (Überschriften, nicht granular):
- **2.1 Beat-/Audio-/Section-Knoten:** 4 Tage — Nodes für Beatgrid, StructureSegment, AudioSegment; 5 Kantentypen laut Studie B.3/B.5
- **2.2 Cluster-Variety:** 2 Tage — Louvain-Community-Detection, Section→Cluster-Mapping in Pacing
- **2.3 Volle Reward-Funktion:** 3 Tage — 5-Komponenten-Reward in `pacing_memory.py`
- **2.4 Persistenz:** 1.5 Tage — JSON+Pickle-Cache unter `data/graph/`
- **2.5 USearch-Integration:** 1 Tag — nur wenn Projekte >5.000 Clips haben
- **2.6 Community-Coloring UI:** 1 Tag — Farb-gruppierte Knoten nach Community

---

## 7. Phase 5 — Deployment (2 Tage)

**Wichtig:** Erst angehen, wenn Phase 0 S3 erfolgreich war. PyInstaller-Bundling ist größter Risikopunkt.

### Aufgabe 5.1 — pb_studio.spec erweitern (3 h)

- **Datei:** `pb_studio.spec`
- **Ergänzungen (exakte Platzierung nach Review der bestehenden Struktur):**
  ```
  # Am Anfang, bei collect_all-Section:
  webengine_datas, webengine_binaries, webengine_hidden = collect_all('PySide6.QtWebEngineCore')
  webchannel_datas, webchannel_binaries, webchannel_hidden = collect_all('PySide6.QtWebChannel')
  webwidgets_datas, webwidgets_binaries, webwidgets_hidden = collect_all('PySide6.QtWebEngineWidgets')

  # Zu all_datas/all_binaries/all_hidden addieren

  # Zu hiddenimports hinzufügen:
  hiddenimports += [
      'PySide6.QtWebEngineWidgets',
      'PySide6.QtWebEngineCore',
      'PySide6.QtWebChannel',
      'networkx',
      'services.graph_service',
      'services.graph_bridge',
      'services.graph_pacing_integration',
      'ui.panels.graph_panel',
  ]

  # Zu datas hinzufügen:
  datas += [
      ('resources/graph/graph_viewer.html', 'resources/graph'),
      ('resources/graph/vis-network.min.js', 'resources/graph'),
      ('resources/graph/vis-network.min.css', 'resources/graph'),
      ('resources/graph/qwebchannel.js', 'resources/graph'),
  ]
  ```
- **Akzeptanz:** `poetry run pyinstaller pb_studio.spec` läuft durch ohne Fehler.
- **Dauer:** 3 h (inkl. Trial-and-Error)

### Aufgabe 5.2 — Clean-Windows-Smoke-Test (3 h)

- **Aktion:**
  1. VirtualBox/Hyper-V mit Windows 11 ohne Python/Dev-Tools
  2. Installer übertragen, installieren
  3. Starten → App muss binnen 10 s starten
  4. Graph-Panel öffnen → vis.js rendert
  5. 30-Minuten-Stabilitätstest: beliebige Nutzung, kein Crash
- **Akzeptanz:** Alle Schritte grün. Log-File (falls implementiert) ohne ERROR-Einträge.
- **Dauer:** 3 h

### Aufgabe 5.3 — Installer-Größen-Impact messen (30 min)

- **Aktion:** Installer vor/nach vergleichen (NSIS-Output-Datei-Größe in MB).
- **Erwartung:** +200–250 MB.
- **Dokumentieren in:** `docs/graph_system_user_guide.md` → „Systemvoraussetzungen"-Abschnitt.
- **Dauer:** 30 min

---

## 8. Rollback-Plan

Falls Phase 1 MVP sich nicht bewährt oder technische Probleme nicht lösbar sind:

### Rollback-Schritte

1. **Feature-Flag global OFF:** `AdvancedPacingSettings.use_graph_diversity = False` als Default hartcoden. Keine Pacing-Regression.
2. **Panel aus Menu entfernen:** Menü-Eintrag „View → Graph-Panel" auskommentieren, Dock wird nie instanziiert.
3. **Services bleiben im Code:** `graph_service.py` etc. bleiben, werden nur nicht mehr aufgerufen. Keine Breaking Changes.
4. **PyInstaller-Ausschluss (falls QtWebEngine-Bundle Probleme macht):** `collect_all`-Zeilen in `.spec` wieder entfernen, Installer schrumpft um ~200 MB.

### Rollback-Dauer

- Disable: 30 min (3 Code-Änderungen + Test)
- Volle Entfernung: 2 h (inkl. Cleanup)

---

## 9. Offene Punkte (vor Phase 0 klären)

1. **Ziel-venv bestätigen:** Aktuell `.venv310`. Gibt es Pläne, auf Python 3.11 + `requirements.txt`-Version zu migrieren? Wenn ja, betrifft das diesen Plan.
2. **Dock vs. Tab:** Option A (Dock) oder B (Tab in EditWorkspace)? Empfehlung: Option A.
3. **Settings-Store-Format:** Existiert `services/settings_store.py` oder wird in Projekt-DB gespeichert? Klärt Integration 1.3.4.
4. **Logging-Target:** Wohin schreibt PB Studio aktuell Logs? Graph-Logs da andocken.
5. **Phase 0 Timing:** Wann wird Phase 0 gestartet? Vorbereitung: VM mit sauberem Windows 11 einrichten (für S3).

---

## 10. Übersicht: Zeit-Budget

| Phase | Aufgaben | Netto-Dauer | Puffer (20 %) | Brutto |
|---|---|---|---|---|
| 0 | Spike S1–S4 + Entscheidung | 13 h | 2.5 h | **~2 Arbeitstage** |
| 1.1 | Graph-Engine Kern | 14 h | 3 h | 2 Tage |
| 1.2 | UI-Panel & vis.js | 10 h | 2 h | 1.5 Tage |
| 1.3 | Pacing-Integration | 7.5 h | 1.5 h | 1 Tag |
| 1.4 | MVP-Abschluss | 8 h | 1.5 h | 1 Tag |
| **Phase 1 gesamt** | | **39.5 h** | **8 h** | **~6 Tage (Netto), 8–10 Tage (mit Code-Review, Tests-Fixes, Puffer)** |
| 5 | Deployment | 6.5 h | 1.5 h | 1 Tag |
| **Gesamt MVP+Deploy** | | | | **~10 Tage** |

Phase 2 (Vollausbau) ist explizit **nicht** Teil dieses MVP-Plans.

---

## 11. Erfolgsmetriken

MVP gilt als erfolgreich wenn:

1. **Funktional:** Ein Projekt mit ≥20 Scenes zeigt einen interaktiven Graph binnen <1 s nach Klick auf „Graph aufbauen".
2. **Stabilität:** Keine Abstürze über 1 h Nutzung (Monitor: Memory-Growth <50 MB in der Stunde).
3. **Anti-Repetition:** Pacing mit Feature AN hat messbar weniger Clip-Wiederholungen als ohne. Messung: Run auf Test-Projekt mit 10 Clips × 3 Scenes = 30 Scenes, Pacing erzeugt Timeline, Repetition-Rate (Anteil konsekutiver Clips mit Graph-Distanz <2) sinkt um ≥30 %.
4. **Deployment:** PyInstaller-Bundle startet auf sauberem Windows 11 und zeigt Graph.
5. **Keine Regression:** Alle bestehenden Pacing-Tests grün.

---

**Plan-Ende. Keine Implementierung startet ohne Go-Entscheidung nach Phase 0.**
