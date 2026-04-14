# Machbarkeitsstudie: Graph-basiertes Wissens- & Ähnlichkeitssystem für PB Studio

**Version:** 1.0 — Fixfertig zur Abarbeitung  
**Datum:** 13. April 2026  
**Projekt:** PB Studio v0.5.0  
**Referenz:** Obsidian_implementierungs-kozept-für_die-app.md  
**Methode:** Full-Stack-Audit × PB-Master × AI-Research  

---

## Executive Summary

**Verdikt: MACHBAR — mit Einschränkungen.**

Das Obsidian-Konzept ist technisch umsetzbar innerhalb der bestehenden PB Studio-Architektur. Die Kernidee — ein heterogener Audio-Video-Graph mit vis.js-Rendering und RL-Pacing-Integration — passt zur vorhandenen Infrastruktur. Es gibt jedoch **sieben kritische Diskrepanzen** zwischen dem Konzept-Dokument und dem Ist-Zustand der App, die vor der Implementierung gelöst werden müssen. Diese Studie dokumentiert jede einzelne, liefert die Lösung und den exakten Implementierungsplan.

**Gesamtaufwand-Schätzung:** 18–24 Arbeitstage (1 Entwickler)  
**Risiko-Einstufung:** MITTEL (3 von 5)  
**Empfehlung:** Phasenweise Umsetzung in 4 Sprints à 5 Tage

---

## Teil A: Ist-Analyse — Was existiert bereits?

### A.1 Bestehende Infrastruktur (verifiziert gegen Codebase)

| Komponente | IST-Zustand | Relevanz für Graph |
|---|---|---|
| **UI-Framework** | PySide6 (Qt 6) — NICHT PyQt6 | ⚠️ KRITISCH — Konzept nennt PyQt6 |
| **Embedding-Modell** | SigLIP (1152-dim) | ⚠️ Konzept rechnet mit 512-dim CLIP |
| **Vektor-DB** | SQLite-basiert (VectorDBService) | ⚠️ Konzept nennt ChromaDB 1.5.6 |
| **GPU** | GTX 1060 6GB (CUDA) | ⚠️ Konzept plant AMD RX 7800 XT + DirectML |
| **Beat-Analyse** | beat_this + Chunked Processing | ✅ Kompatibel |
| **Struktur-Erkennung** | Multi-Feature (RMS, Spectral, Bass) | ✅ Kompatibel |
| **Stem-Separation** | Demucs v4 | ✅ Kompatibel |
| **Scene Detection** | PySceneDetect + RAFT Optical Flow | ✅ Kompatibel |
| **Vision-Analyse** | SigLIP + Moondream2/Gemma 4 via Ollama | ✅ Kompatibel |
| **Pacing-Engine** | DJ-Pacing mit OTIO Timeline | ✅ Kompatibel |
| **Pacing-Strategist** | Gemma 4 E4B via Ollama | ✅ Kompatibel |
| **KI-Memory** | AIPacingMemory (SQLAlchemy) | ✅ Kompatibel |
| **DB-System** | SQLite + SQLAlchemy, WAL-Modus | ✅ Kompatibel |
| **Deployment** | PyInstaller + NSIS (Windows 11) | ⚠️ +200 MB durch QWebEngine |
| **Model-Manager** | Singleton, GPU_LOAD_LOCK, GPU_EXECUTION_LOCK | ✅ Kompatibel |
| **Python** | 3.11.9 (venv) | ✅ Kompatibel |

### A.2 Die sieben kritischen Diskrepanzen

| # | Diskrepanz | Konzept sagt | App hat | Schwere |
|---|---|---|---|---|
| D-1 | UI-Framework | PyQt6 + QWebEngineView + QWebChannel | PySide6 (Qt 6) | HOCH |
| D-2 | Embedding-Dimension | 512-dim (CLIP) | 1152-dim (SigLIP) | MITTEL |
| D-3 | Vektor-Datenbank | ChromaDB 1.5.6 | SQLite-basiert (VectorDBService) | MITTEL |
| D-4 | GPU-Architektur | AMD RX 7800 XT + DirectML | NVIDIA GTX 1060 + CUDA | HOCH |
| D-5 | Performance-Zahlen | 5.000 Clips in <200ms (CPU) | 1152-dim statt 512 → ~4.5× mehr Daten | NIEDRIG |
| D-6 | HNSW-Extraktion | ChromaDB HNSW-Index | Kein HNSW vorhanden | NIEDRIG |
| D-7 | Installer-Größe | +200 MB via QtWebEngine | PyInstaller-Bundle | MITTEL |

---

## Teil B: Auflösung jeder Diskrepanz

### B.1 Diskrepanz D-1: PySide6 statt PyQt6

**Problem:** Das Konzept nutzt `PyQt6.QtWebEngineWidgets.QWebEngineView` und `PyQt6.QtWebChannel.QWebChannel`. PB Studio verwendet PySide6.

**Lösung:** PySide6 hat **identische APIs** — nur die Import-Pfade ändern sich:

| Konzept (PyQt6) | PB Studio (PySide6) |
|---|---|
| `from PyQt6.QtWebEngineWidgets import QWebEngineView` | `from PySide6.QtWebEngineWidgets import QWebEngineView` |
| `from PyQt6.QtWebChannel import QWebChannel` | `from PySide6.QtWebChannel import QWebChannel` |
| `from PyQt6.QtCore import QObject, pyqtSlot` | `from PySide6.QtCore import QObject, Slot` |
| `@pyqtSlot(str)` | `@Slot(str)` |

**Zusätzliche Abhängigkeit:** `PySide6-WebEngine` muss installiert werden:
```
pip install PySide6-WebEngine==6.11.0
```

**Prüfung:** PySide6 6.11.0 existiert und hat PySide6-WebEngine als separates Paket. Die API-Kompatibilität ist 1:1.

**Aufwand:** 0.5 Tage  
**Risiko:** NIEDRIG — reines Suchen-und-Ersetzen

---

### B.2 Diskrepanz D-2: 1152-dim SigLIP statt 512-dim CLIP

**Problem:** Das Konzept rechnet mit 512-dimensionalen CLIP-Vektoren. PB Studio nutzt SigLIP mit 1152 Dimensionen. Die Ähnlichkeitsmatrix für 5.000 Clips wächst von ~100 MB auf ~450 MB.

**Lösung:** Kein Problem. Die Berechnung bleibt identisch:

| Metrik | 512-dim (CLIP) | 1152-dim (SigLIP) | Faktor |
|---|---|---|---|
| Embedding-Matrix (5K Clips) | ~10 MB | ~22 MB | 2.25× |
| Volle Ähnlichkeitsmatrix | ~100 MB | ~100 MB | 1× (gleiche Clip-Anzahl) |
| BLAS-Matmul-Zeit | 50–200 ms | 100–450 ms | ~2.25× |
| k-NN (HNSW, USearch) | 5–30 ms | 10–60 ms | ~2× |

**Wichtig:** Die Ähnlichkeitsmatrix ist immer N×N (nicht N×D), also bleibt sie bei 5.000×5.000 = 100 MB unverändert. Nur die Matmul dauert proportional zur Dimension länger — aber 450 ms auf CPU ist immer noch völlig akzeptabel.

**Anpassung im Code:**
- `EMBEDDING_DIM` in VectorDBService ist bereits `1152` — passt
- Alle Kosinusähnlichkeits-Berechnungen funktionieren dimensionsunabhängig
- USearch/faiss-cpu arbeiten mit beliebigen Dimensionen

**Aufwand:** 0 Tage (keine Änderung nötig)  
**Risiko:** KEIN RISIKO

---

### B.3 Diskrepanz D-3: SQLite-VectorDB statt ChromaDB

**Problem:** Das Konzept nutzt ChromaDB 1.5.6 mit `collection.query()` für Batch-k-NN. PB Studio hat eine eigene SQLite-basierte VectorDBService (vektordb_service.py) mit `search()` und `get_all_embeddings()`.

**Lösung — Option A (EMPFOHLEN): Bestehende VectorDBService erweitern**

Die bestehende VectorDBService hat bereits `get_all_embeddings()` → (matrix, metadata). Der Graph-Aufbau nutzt diese Methode direkt:

```
# Pseudocode — KEIN neues Framework nötig
embeddings, metadata = vector_db.get_all_embeddings()
# L2-Normalisierung
norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
X_norm = embeddings / norms
# Volle Ähnlichkeitsmatrix ODER k-NN via USearch
similarity = X_norm @ X_norm.T
```

**Vorteile gegenüber ChromaDB:**
- Keine neue Dependency
- Kein zweites Datenbank-System
- Kein ChromaDB-spezifisches File-Locking-Problem auf Windows
- Bestehende Thread-Safety (Write-Lock, Cache) wird genutzt

**Notwendige Erweiterung der VectorDBService:**
1. Neue Methode `batch_knn(k=20)` die `get_all_embeddings()` nutzt und k-NN-Paare zurückgibt
2. Neuer Return-Type: `list[tuple[str, str, float]]` → (clip_id_a, clip_id_b, similarity)

**Lösung — Option B (NICHT EMPFOHLEN): ChromaDB zusätzlich installieren**

ChromaDB 1.5.6 bringt ~30 Dependencies mit (inkl. eigenes hnswlib, protobuf, pydantic). Auf Windows gab es historisch Probleme mit Tokio/Rust-Runtime-Konflikten — genau der Grund, warum LanceDB durch die SQLite-Lösung ersetzt wurde (siehe Docstring in vector_db_service.py Zeile 3-4).

**Entscheidung:** Option A. Keine neue DB.

**Aufwand:** 1 Tag  
**Risiko:** NIEDRIG

---

### B.4 Diskrepanz D-4: NVIDIA GTX 1060 (CUDA) statt AMD RX 7800 XT (DirectML)

**Problem:** Das Konzept plant für AMD + DirectML. PB Studio läuft auf NVIDIA GTX 1060 mit CUDA.

**Lösung:** Die GPU-Diskrepanz betrifft NUR die CLIP/SigLIP-Inferenz. Der gesamte Graph-Code läuft auf CPU. Das ist sogar ein Vorteil — denn PB Studio nutzt bereits ModelManager mit GPU_LOAD_LOCK und GPU_EXECUTION_LOCK für VRAM-Management auf der 6 GB GTX 1060.

**Betroffene Stellen:**
- SigLIP-Inferenz: Nutzt bereits CUDA via PyTorch → keine Änderung
- Kosinusähnlichkeit: CPU (NumPy BLAS) → keine GPU-Abhängigkeit
- NetworkX: Pure Python → keine GPU-Abhängigkeit
- vis.js Rendering: Browser-Engine → keine GPU-Abhängigkeit
- USearch/faiss-cpu: CPU-only by design → keine Änderung

**Zusätzliche VRAM-Überlegung:** Die Graph-Konstruktion braucht KEIN VRAM. Sie läuft vollständig im RAM. Bei 5.000 Clips mit 1152-dim Embeddings: ~22 MB RAM für die Matrix + ~100 MB für die Ähnlichkeitsmatrix = ~122 MB. Irrelevant.

**Aufwand:** 0 Tage (keine Änderung nötig)  
**Risiko:** KEIN RISIKO

---

### B.5 Diskrepanz D-5: Performance-Neuberechnung für 1152-dim

**Angepasste Performance-Tabelle (GTX 1060, Python 3.11, 1152-dim SigLIP):**

| Operation | Konzept (512-dim) | Realität (1152-dim) | Akzeptabel? |
|---|---|---|---|
| Volle Matmul (5K Clips) | 50–200 ms | 100–450 ms | ✅ Ja |
| USearch k-NN (5K, k=20) | 5–30 ms | 10–60 ms | ✅ Ja |
| NetworkX Graph-Aufbau | <100 ms | <100 ms | ✅ Ja |
| vis.js Initial Render (5K Knoten) | ~2 s | ~2 s | ✅ Ja |
| Gesamte Pipeline | <2 s | <3 s | ✅ Ja |

**Engpass-Analyse:** Der reale Engpass ist NICHT die Berechnung, sondern die **QWebEngineView-Initialisierung** (Chromium-Start: 500–1500 ms beim ersten Öffnen). Danach sind Updates inkrementell und in <100 ms.

**Aufwand:** 0 Tage  
**Risiko:** KEIN RISIKO

---

### B.6 Diskrepanz D-6: HNSW-Extraktion

**Problem:** Das Konzept beschreibt HNSW-Kanten-Extraktion aus ChromaDB. Da wir ChromaDB nicht nutzen (B.3), fällt dieser Schritt weg.

**Lösung:** Direkter k-NN via NumPy oder USearch:

1. **Für ≤5.000 Clips:** Brute-Force via NumPy-Matmul (100–450 ms)
2. **Für >5.000 Clips:** USearch HNSW-Index (10–60 ms)

USearch wird nur installiert wenn die Clip-Anzahl >5.000 beträgt. Für die meisten DJ-Sets (20–200 Clips) ist Brute-Force millisekundengenau.

**Aufwand:** 0.5 Tage (USearch als optionale Dependency)  
**Risiko:** KEIN RISIKO

---

### B.7 Diskrepanz D-7: Installer-Größe (+200 MB durch QtWebEngine)

**Problem:** PySide6-WebEngine bringt ~200 MB Chromium-Engine mit. Der aktuelle Installer ist via PyInstaller gebaut.

**Lösung — Zwei Optionen:**

**Option A (EMPFOHLEN): WebEngine akzeptieren**
- +200 MB ist für eine Desktop-App mit KI-Modellen (SigLIP: ~400 MB, Demucs: ~300 MB, Gemma: ~5 GB) vernachlässigbar
- Der Installer ist ohnehin >1 GB
- vis.js bietet Force-Directed-Layout, Clustering, Physics out-of-the-box

**Option B (Fallback): Native QGraphicsView**
- Kein WebEngine nötig
- Erfordert manuelle Implementierung von Force-Directed-Physics, Edge-Routing, Clustering
- Geschätzter Mehraufwand: +15 Arbeitstage
- NICHT EMPFOHLEN für MVP

**PyInstaller-Anpassung:**
```
# In .spec-Datei hinzufügen:
hiddenimports=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel']
datas=[('path/to/vis-network.min.js', 'resources/graph/')]
```

**Aufwand:** 0.5 Tage  
**Risiko:** NIEDRIG

---

## Teil C: Vollständiger Implementierungsplan

### Phase 0: Dependencies & Setup (Tag 1)

#### Schritt 0.1: Neue Pakete installieren

```
pip install networkx[default]==3.6.1
pip install igraph==1.0.0
pip install PySide6-WebEngine==6.11.0
pip install usearch==2.23.0       # Optional: nur wenn >5K Clips erwartet
```

**Prüfung:** Alle Pakete haben vorkompilierte Windows-Wheels für Python 3.11.

#### Schritt 0.2: requirements.txt erweitern

Folgende Zeilen hinzufügen:
```
networkx[default]==3.6.1; python_version >= "3.11" and python_version < "3.13"
igraph==1.0.0; python_version >= "3.11" and python_version < "3.13"
PySide6-WebEngine==6.11.0; python_version >= "3.11" and python_version < "3.13"
```

#### Schritt 0.3: Verzeichnisstruktur anlegen

```
services/
├── graph_service.py              # NEU: Graph-Engine (NetworkX)
├── graph_bridge.py               # NEU: PySide6 ↔ vis.js Bridge
├── graph_persistence.py          # NEU: JSON/Pickle Persistenz
├── graph_pacing_integration.py   # NEU: Graph → Pacing-Engine Adapter

resources/
├── graph/
│   ├── graph_viewer.html         # NEU: vis.js Frontend
│   ├── vis-network.min.js        # NEU: vis.js Bibliothek (9.x)
│   └── vis-network.min.css       # NEU: vis.js Styles
```

#### Schritt 0.4: vis.js Ressourcen beschaffen

vis-network 9.x von CDN herunterladen und in `resources/graph/` ablegen:
- `https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js` (~250 KB)
- `https://unpkg.com/vis-network@9.1.9/dist/dist/vis-network.min.css` (~30 KB)

---

### Phase 1: Graph-Engine Service (Tag 2–4)

#### Schritt 1.1: graph_service.py — Kern des Graph-Systems

**Datei:** `services/graph_service.py`

**Klasse:** `GraphService` (Singleton, analog zu VectorDBService)

**Verantwortlichkeiten:**
- NetworkX-Graph erstellen und verwalten
- k-NN-Kanten aus Embedding-Ähnlichkeit berechnen
- Heterogene Knoten (4 Typen) und Kanten (5 Typen) verwalten
- Community-Detection und Clustering
- Graph-Metriken (Centrality, Clustering-Koeffizient)

**Knoten-Typen und ihre Datenquellen:**

| Knotentyp | ID-Schema | Attribute | Datenquelle in PB Studio |
|---|---|---|---|
| `video_clip` | `v_{video_clip_id}_{scene_index}` | embedding (1152-d), motion_score, duration, ai_mood, ai_tags, keyframe_path | Scene-Tabelle + VectorDBService |
| `beat` | `b_{audio_track_id}_{beat_index}` | time, bpm, strength, downbeat | Beatgrid-Tabelle |
| `audio_segment` | `a_{audio_track_id}_{segment_index}` | rms_energy, spectral_centroid, onset_density, stem_ratios | StructureSegment-Tabelle + SpectralAnalysisService |
| `music_section` | `s_{audio_track_id}_{section_index}` | type (DROP/BUILDUP/...), energy, confidence, bass_energy | StructureSegment-Tabelle |

**Kanten-Typen und ihre Gewichtsformeln:**

| Kantentyp | Gewichtsformel | Quelle |
|---|---|---|
| `video↔video` | `cos(SigLIP_i, SigLIP_j)` — Schwellenwert >0.3 | VectorDBService.get_all_embeddings() |
| `audio↔audio` | `exp(-|t_i - t_j| / τ)` mit τ=2.0 | Beatgrid-Timestamps |
| `beat↔video` | `exp(-Δt² / σ²)` mit σ=0.083 (≈2 Frames @ 24fps) | Beat-Time vs. Scene start/end |
| `audio_seg↔video` | `corr(rms_envelope, motion_energy)` | StructureResult + Scene.energy |
| `section↔video_cluster` | `jaccard(clip_set, section_clips)` | Section-Zeiten vs. Clip-Zeiten |

**Methoden-Signatur:**

```
class GraphService:
    # Singleton-Pattern (analog VectorDBService.__new__)

    def build_full_graph(project_id: int) -> nx.Graph
        # Lädt alle Daten, baut den kompletten heterogenen Graphen

    def build_video_similarity_graph(k: int = 20, threshold: float = 0.3) -> nx.Graph
        # Nur Video↔Video Kanten (schnell, für Preview)

    def add_clip_incremental(clip_id: int, scene_index: int) -> None
        # Fügt einen neuen Clip hinzu + k-NN-Kanten

    def get_communities() -> list[set[str]]
        # Louvain Community Detection

    def get_cluster_for_node(node_id: str) -> set[str]
        # Alle Nachbarn eines Knotens

    def get_graph_distance(node_a: str, node_b: str) -> int
        # Shortest Path Länge (für Anti-Repetitions-Constraint)

    def get_centrality_scores() -> dict[str, float]
        # Betweenness Centrality aller Knoten

    def get_vis_js_data() -> dict
        # Export als vis.js-kompatibles JSON {nodes: [...], edges: [...]}

    def rebuild() -> None
        # Vollständiger Neuaufbau (nach >100 neuen Clips)
```

**Interne k-NN-Berechnung:**

```
def _compute_knn_edges(embeddings: np.ndarray, metadata: list[dict], 
                        k: int = 20, threshold: float = 0.3) -> list[tuple]:
    # 1. L2-Normalisierung
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
    X_norm = embeddings / norms

    # 2. Volle Ähnlichkeitsmatrix (für ≤5K Clips)
    if len(embeddings) <= 5000:
        sim_matrix = X_norm @ X_norm.T
        # Top-k pro Zeile extrahieren
        edges = []
        for i in range(len(embeddings)):
            top_k_indices = np.argpartition(-sim_matrix[i], k+1)[:k+1]
            for j in top_k_indices:
                if i != j and sim_matrix[i, j] > threshold:
                    edges.append((metadata[i]['id'], metadata[j]['id'], 
                                  float(sim_matrix[i, j])))
        return edges

    # 3. USearch für >5K Clips (optional)
    else:
        from usearch.index import Index
        index = Index(ndim=embeddings.shape[1], metric='cos')
        index.add(np.arange(len(embeddings)), X_norm)
        # ... Batch-Search
```

**Thread-Safety:** Analog zu VectorDBService mit `threading.Lock()` für Schreiboperationen und In-Memory-Cache für Lesezugriffe.

---

#### Schritt 1.2: graph_persistence.py — Speicherung

**Datei:** `services/graph_persistence.py`

**Speicherort:** `{PROJECT_ROOT}/data/graph/`

**Dateien:**
- `graph.json` — Kanonisches Format (nx.node_link_data)
- `graph.pkl` — Schneller Cache (pickle)

**Auto-Save-Logik:**
- Pickle nach jedem `add_clip_incremental()` (schnell: <50 ms)
- JSON nach jedem 10. Clip ODER bei manuellem Save
- Beim Laden: Pickle zuerst versuchen, Fallback auf JSON

**Projekt-Switch:** `set_project()` in session.py muss erweitert werden um `GraphService._instance = None` (Singleton-Reset, analog zu VectorDBService).

**JSON-Dateigröße (geschätzt):**
- 100 Clips, k=20: ~0.2 MB
- 1.000 Clips, k=20: ~2 MB
- 5.000 Clips, k=20: ~10 MB

---

#### Schritt 1.3: Datenbank-Schema-Erweiterung

**KEINE neuen Tabellen nötig.** Der Graph wird aus bestehenden Tabellen gebaut:
- `scenes` → Video-Clip-Knoten
- `beatgrids` → Beat-Knoten
- `structure_segments` → Audio-Segment-Knoten + Musik-Sektions-Knoten
- `clip_embeddings` (SQLite VectorDB) → Embedding-Vektoren

**Optional:** Ein neues Feld in der `scenes`-Tabelle für Graph-Cluster-Zuordnung:
```sql
ALTER TABLE scenes ADD COLUMN graph_cluster_id INTEGER DEFAULT NULL;
```

Dies erfordert eine Alembic-Migration ODER einen Eintrag in `migrations.py`.

---

### Phase 2: vis.js Frontend & Bridge (Tag 5–9)

#### Schritt 2.1: graph_viewer.html — vis.js Frontend

**Datei:** `resources/graph/graph_viewer.html`

**Aufbau:**
```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="vis-network.min.css" />
    <script src="vis-network.min.js"></script>
    <script src="qwebchannel.js"></script>  <!-- Von Qt bereitgestellt -->
    <style>
        body { margin: 0; overflow: hidden; background: transparent; }
        #graph-container { width: 100%; height: 100vh; }
    </style>
</head>
<body>
    <div id="graph-container"></div>
    <script>
        // ... vis.js Setup + QWebChannel Bridge
    </script>
</body>
</html>
```

**vis.js Konfiguration (Performance-optimiert für 5K Knoten):**

```javascript
var options = {
    physics: {
        solver: 'barnesHut',           // O(n log n) statt O(n²)
        barnesHut: {
            gravitationalConstant: -2000,
            centralGravity: 0.3,
            springLength: 95,
            springConstant: 0.04,
            damping: 0.09
        },
        stabilization: {
            iterations: 150,           // Begrenzt auf 150
            updateInterval: 25
        }
    },
    edges: {
        smooth: false,                 // KRITISCH: Smooth Edges deaktivieren
        color: { inherit: 'both' },
        width: 0.5
    },
    nodes: {
        shape: 'dot',
        scaling: { min: 5, max: 20 }
    },
    groups: {                          // Farben pro Knotentyp
        video_clip:    { color: '#4FC3F7', shape: 'dot' },
        beat:          { color: '#FF7043', shape: 'diamond' },
        audio_segment: { color: '#66BB6A', shape: 'triangle' },
        music_section: { color: '#AB47BC', shape: 'square' }
    },
    interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: true
    },
    clustering: {                      // Auto-Clustering ab 50 Knoten
        enabled: true,
        clusterByConnection: true
    }
};
```

**Knoten-Darstellung:**

| Knotentyp | Form | Farbe | Label | Tooltip |
|---|---|---|---|---|
| video_clip | Kreis (dot) | Hellblau #4FC3F7 | Scene-Index | Video-Pfad, Dauer, Motion-Score, AI-Mood |
| beat | Diamant | Orange #FF7043 | Beat-Index | Zeit, BPM, Downbeat? |
| audio_segment | Dreieck | Grün #66BB6A | Segment-Typ | RMS, Spectral Centroid |
| music_section | Quadrat | Lila #AB47BC | Section-Label | DROP/BUILDUP/..., Energie |

**Interaktions-Events (JavaScript → Python):**

| Event | JavaScript | Python-Callback |
|---|---|---|
| Knoten-Klick | `network.on('click', ...)` | `bridge.on_node_clicked(node_id)` |
| Knoten-Doppelklick | `network.on('doubleClick', ...)` | `bridge.on_node_double_clicked(node_id)` |
| Knoten-Hover | `network.on('hoverNode', ...)` | `bridge.on_node_hovered(node_id)` |
| Selektion geändert | `network.on('selectNode', ...)` | `bridge.on_selection_changed(node_ids)` |
| Cluster geöffnet | `network.on('openCluster', ...)` | `bridge.on_cluster_opened(cluster_id)` |

**Python → JavaScript Aktionen:**

| Aktion | Python-Methode | JavaScript-Funktion |
|---|---|---|
| Graph laden | `bridge.push_graph_data(G)` | `updateGraph(data)` |
| Knoten hervorheben | `bridge.highlight_node(id)` | `highlightNode(id)` |
| Cluster fokussieren | `bridge.focus_cluster(ids)` | `focusOnNodes(ids)` |
| Kanten filtern | `bridge.set_edge_threshold(min)` | `filterEdges(minWeight)` |
| Screenshot | `bridge.capture_screenshot()` | `captureCanvas()` |

---

#### Schritt 2.2: graph_bridge.py — PySide6 ↔ vis.js Kommunikation

**Datei:** `services/graph_bridge.py`

**Klasse:** `GraphBridge(QObject)` — erbt von QObject für Signal/Slot-System

**Kernlogik:**

```
class GraphBridge(QObject):
    # Signals (PySide6-Syntax)
    node_clicked = Signal(str)          # node_id
    node_double_clicked = Signal(str)   # node_id
    selection_changed = Signal(list)    # [node_id, ...]

    # Slots (JavaScript → Python)
    @Slot(str)
    def on_node_clicked(self, node_id: str):
        # Video-Clip in Timeline selektieren
        # Preview starten
        self.node_clicked.emit(node_id)

    @Slot(str)
    def on_node_double_clicked(self, node_id: str):
        # Clip zur Timeline hinzufügen
        self.node_double_clicked.emit(node_id)

    # Methoden (Python → JavaScript)
    def push_graph_data(self, G: nx.Graph):
        data = GraphService().get_vis_js_data()
        js_code = f"updateGraph({json.dumps(data)})"
        self.web_view.page().runJavaScript(js_code)

    def highlight_node(self, node_id: str):
        self.web_view.page().runJavaScript(f"highlightNode('{node_id}')")
```

**Integration in die UI:**

Der GraphBridge wird als neues Panel in das Hauptfenster eingebettet:

```
class GraphPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.web_view = QWebEngineView()
        self.channel = QWebChannel()
        self.bridge = GraphBridge()

        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        html_path = Path(__file__).parent.parent / "resources" / "graph" / "graph_viewer.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)
```

**UI-Platzierung:** Das GraphPanel wird als neues Tab neben der Timeline eingefügt, oder als abkoppelbares Dock-Widget (QDockWidget).

---

#### Schritt 2.3: AMD GPU Fallback für QWebEngineView

Da die GTX 1060 eine NVIDIA-Karte ist, entfallen die AMD-spezifischen D3D11-Probleme. Aber als defensiver Fallback:

```python
import os
# Setze Software-Rendering als Fallback bei GPU-Problemen
# NUR aktivieren wenn User Rendering-Probleme meldet
# os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
```

Dies sollte als Setting in `settings_store.py` verfügbar sein:
```json
{
  "graph": {
    "software_rendering": false,
    "physics_enabled": true,
    "edge_threshold": 0.3,
    "max_visible_nodes": 5000
  }
}
```

---

### Phase 3: Pacing-Integration (Tag 10–14)

#### Schritt 3.1: graph_pacing_integration.py — Graph → Pacing Adapter

**Datei:** `services/graph_pacing_integration.py`

Dieser Adapter verbindet den Graphen mit der bestehenden Pacing-Engine.

**Kernfunktionalität:**

**3.1.1 Anti-Repetitions-Constraint**

Das Konzept definiert: "Zwei Clips dürfen nur dann konsekutiv stehen, wenn ihr Graph-Abstand ≥ 2 im k-NN-Ähnlichkeitsgraphen beträgt."

Integration in `pacing_edit_helpers.py` → `_match_video_for_segment()`:

```
def is_repetition_safe(clip_a_id: int, clip_b_id: int, 
                        graph: nx.Graph, min_distance: int = 2) -> bool:
    node_a = f"v_{clip_a_id}"
    node_b = f"v_{clip_b_id}"
    try:
        distance = nx.shortest_path_length(graph, node_a, node_b)
        return distance >= min_distance
    except nx.NetworkXNoPath:
        return True  # Keine Verbindung = sicher
```

**Einbau-Punkt:** In `_match_video_for_segment()` (pacing_edit_helpers.py) wird nach dem Fitness-Scoring ein zusätzlicher Filter eingefügt:

```
# Bestehender Code: candidates = sorted(scored_clips, ...)
# NEU: Anti-Repetitions-Filter
if graph_service and last_clip_id:
    candidates = [c for c in candidates 
                  if is_repetition_safe(last_clip_id, c.id, graph)]
```

**3.1.2 Cluster-basiertes Section-Mapping**

Das Konzept definiert: "Clips im selben dichten Cluster sollten durch Clips aus anderen Clustern getrennt werden."

Integration in `pacing_strategist.py`:

```
def get_cluster_variety_schedule(sections: list[Section], 
                                  graph: nx.Graph) -> dict[str, list[int]]:
    communities = GraphService().get_communities()
    schedule = {}
    for section in sections:
        # DROP → Abwechslung zwischen Clustern (hohe Diversität)
        # BREAKDOWN → Clips aus einem Cluster (visuelle Kohärenz)
        if section.label == "DROP":
            schedule[section.id] = _interleave_clusters(communities)
        elif section.label == "BREAKDOWN":
            schedule[section.id] = _single_cluster(communities, 
                                                    calm_cluster=True)
    return schedule
```

**3.1.3 Reward-Funktion-Erweiterung**

Das Konzept definiert eine erweiterte Reward-Funktion:

```
R_total = α·R_beat + β·R_diversity + γ·R_represent + δ·R_contrast + ε·R_coherence
```

Integration in `pacing_memory.py` → `record_rl_feedback()`:

| Reward-Komponente | Gewicht | Berechnung | Datenquelle |
|---|---|---|---|
| R_beat | α = 0.35 | `exp(-|Δt|²/σ²)` | Beatgrid-Timestamps |
| R_diversity | β = 0.25 | `mean(||f_i - f_{i+1}||)` über Graph-Distanzen | GraphService.get_graph_distance() |
| R_represent | γ = 0.15 | `exp(-mean(min_j ||f_i - f̂_j||))` | VectorDBService.search() |
| R_contrast | δ = 0.15 | `penalty wenn cos > 0.85` | GraphService (Kantengewicht) |
| R_coherence | ε = 0.10 | `corr(audio_energy, visual_motion)` | StructureResult + Scene.energy |

**Einbau-Punkt:** Neue Methode `compute_graph_reward()` in `pacing_memory.py`:

```
def compute_graph_reward(timeline_segments: list[TimelineSegment],
                          graph: nx.Graph,
                          beat_positions: list[float]) -> float:
    r_beat = _compute_beat_alignment(timeline_segments, beat_positions)
    r_diversity = _compute_diversity(timeline_segments, graph)
    r_represent = _compute_representativeness(timeline_segments)
    r_contrast = _compute_anti_repetition(timeline_segments, graph)
    r_coherence = _compute_coherence(timeline_segments)

    return (0.35 * r_beat + 0.25 * r_diversity + 0.15 * r_represent +
            0.15 * r_contrast + 0.10 * r_coherence)
```

---

#### Schritt 3.2: Erweiterte PacingSettings

In `pacing_beat_grid.py` → `AdvancedPacingSettings` erweitern:

```
@dataclass
class AdvancedPacingSettings:
    # ... bestehende Felder ...

    # NEU: Graph-basierte Einstellungen
    use_graph_diversity: bool = True       # Anti-Repetitions-Constraint
    graph_min_distance: int = 2            # Mindest-Graph-Abstand
    cluster_variety: bool = True           # Cluster-basiertes Section-Mapping
    diversity_weight: float = 0.25         # β in Reward-Funktion
    contrast_threshold: float = 0.85       # Anti-Repetitions-Schwellenwert
```

---

### Phase 4: UI-Integration & Settings (Tag 15–18)

#### Schritt 4.1: Graph-Panel in Hauptfenster

**Platzierung:** Neues Tab "Graph" neben "Timeline" und "Media Pool"

**Toolbar-Buttons:**

| Button | Icon | Aktion |
|---|---|---|
| "Graph aufbauen" | 🔄 | `GraphService().build_full_graph(project_id)` |
| "Nur Videos" | 🎬 | `GraphService().build_video_similarity_graph()` |
| "Communities" | 🏘️ | `GraphService().get_communities()` → farblich hervorheben |
| "Schwellenwert" | ⚖️ | Slider → `bridge.set_edge_threshold(value)` |
| "Zoom to Fit" | 🔍 | `bridge.zoom_to_fit()` |
| "Export PNG" | 📷 | `bridge.capture_screenshot()` |

#### Schritt 4.2: Interaktions-Workflows

**Workflow 1: Clip-Preview aus Graph**
1. User klickt Knoten im Graph → `on_node_clicked("v_5_3")`
2. Python extrahiert video_clip_id=5, scene_index=3
3. Video-Preview startet bei scene_start mit scene_end als Ende
4. Knoten wird im Graph hervorgehoben

**Workflow 2: Clip zur Timeline hinzufügen**
1. User doppelklickt Knoten → `on_node_double_clicked("v_5_3")`
2. Clip wird an nächster freier Position in Timeline eingefügt
3. Graph-Nachbarn werden farblich als "verwandt" markiert

**Workflow 3: Ähnliche Clips finden**
1. User rechtsklickt Knoten → Kontextmenü "Ähnliche anzeigen"
2. k-NN-Nachbarn werden hervorgehoben
3. Nicht-Nachbarn werden ausgegraut

**Workflow 4: Graph-gestütztes Auto-Edit**
1. User klickt "Auto-Edit mit Graph"
2. Pacing-Engine nutzt Graph für Anti-Repetition + Cluster-Variety
3. Timeline wird befüllt mit Graph-optimierter Clip-Reihenfolge

#### Schritt 4.3: Settings-Erweiterung

In `settings_store.py` → neuer Abschnitt:

```json
{
  "graph": {
    "enabled": true,
    "auto_build_on_analysis": true,
    "similarity_threshold": 0.3,
    "max_neighbors_k": 20,
    "physics_enabled": true,
    "show_beat_nodes": false,
    "show_audio_nodes": false,
    "show_section_nodes": true,
    "software_rendering": false,
    "anti_repetition_distance": 2,
    "cluster_variety_enabled": true
  }
}
```

---

### Phase 5: Testing & Validation (Tag 19–22)

#### Schritt 5.1: Unit-Tests

| Test | Beschreibung | Erwartetes Ergebnis |
|---|---|---|
| `test_graph_build_empty` | Graph mit 0 Clips | Leerer Graph, kein Fehler |
| `test_graph_build_1_clip` | Graph mit 1 Clip | 1 Knoten, 0 Kanten |
| `test_graph_build_100_clips` | Graph mit 100 Clips, k=20 | 100 Knoten, ≤2000 Kanten |
| `test_knn_symmetry` | k-NN-Ähnlichkeit | cos(A,B) == cos(B,A) |
| `test_knn_threshold` | Schwellenwert 0.3 | Keine Kanten mit weight < 0.3 |
| `test_anti_repetition` | Konsekutive Clips | Graph-Distanz ≥ 2 |
| `test_community_detection` | Louvain auf 100 Clips | ≥2 Communities |
| `test_persistence_json` | Save/Load-Zyklus | Identischer Graph |
| `test_persistence_pickle` | Save/Load-Zyklus | Identischer Graph |
| `test_incremental_add` | 1 Clip nachträglich | Knoten + Kanten hinzugefügt |
| `test_vis_js_export` | JSON-Export | Valides vis.js-Format |
| `test_bridge_signals` | Klick-Event | Signal wird emittiert |
| `test_reward_function` | Diverse Timeline | Reward > 0.5 |
| `test_reward_repetitive` | Repetitive Timeline | Reward < 0.3 |

#### Schritt 5.2: Performance-Tests

| Test | Input | Erwartetes Ergebnis | Grenzwert |
|---|---|---|---|
| `perf_knn_100` | 100 Clips, 1152-dim | <50 ms | 200 ms |
| `perf_knn_1000` | 1.000 Clips, 1152-dim | <200 ms | 1.000 ms |
| `perf_knn_5000` | 5.000 Clips, 1152-dim | <500 ms | 2.000 ms |
| `perf_graph_build_100` | 100 Clips | <100 ms | 500 ms |
| `perf_graph_build_1000` | 1.000 Clips | <500 ms | 2.000 ms |
| `perf_vis_js_render_100` | 100 Knoten | <500 ms | 2.000 ms |
| `perf_vis_js_render_5000` | 5.000 Knoten | <3.000 ms | 5.000 ms |
| `perf_persistence_save` | 1.000 Knoten Graph | <200 ms | 1.000 ms |
| `perf_persistence_load` | 1.000 Knoten Graph | <100 ms | 500 ms |

#### Schritt 5.3: Integrations-Tests

| Test | Szenario | Prüfpunkte |
|---|---|---|
| `integ_full_pipeline` | 10 Videos importieren → analysieren → Graph bauen → Auto-Edit | Graph wird gebaut, Anti-Repetition funktioniert |
| `integ_project_switch` | Projekt wechseln | Graph-Singleton wird zurückgesetzt, neuer Graph geladen |
| `integ_clip_delete` | Video löschen | Knoten + Kanten werden entfernt |
| `integ_concurrent_access` | Graph-Build während UI-Nutzung | Kein Freeze, Progress-Bar |
| `integ_large_project` | 500 Videos mit je 10 Szenen | 5.000 Knoten, stabile Interaktion |

---

### Phase 6: Deployment-Anpassungen (Tag 23–24)

#### Schritt 6.1: PyInstaller-Konfiguration

In der `.spec`-Datei:

```python
# Neue Hidden Imports
hiddenimports=[
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngineCore',
    'networkx',
    'igraph',
]

# Neue Data-Files
datas=[
    ('resources/graph/graph_viewer.html', 'resources/graph'),
    ('resources/graph/vis-network.min.js', 'resources/graph'),
    ('resources/graph/vis-network.min.css', 'resources/graph'),
]
```

#### Schritt 6.2: NSIS-Installer

Keine Änderungen nötig — die neuen Dateien werden automatisch durch PyInstaller eingebunden.

#### Schritt 6.3: Größen-Impact

| Komponente | Größe | Kommentar |
|---|---|---|
| PySide6-WebEngine | ~200 MB | Chromium-Engine |
| NetworkX | ~5 MB | Pure Python |
| igraph | ~10 MB | C-Binary |
| vis-network.min.js | ~250 KB | JavaScript |
| **Total** | **~215 MB** | Installer wächst von ~1.2 GB auf ~1.4 GB |

---

## Teil D: Risiko-Matrix

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|---|---|---|---|
| QWebEngineView-Rendering-Probleme auf bestimmten GPUs | MITTEL | HOCH | Software-Rendering-Fallback (`--disable-gpu`) |
| vis.js Performance bei >5K Knoten | NIEDRIG | MITTEL | Sigma.js als Fallback, Clustering aktivieren |
| Memory-Leak in QWebEngineView bei langem Betrieb | MITTEL | MITTEL | Periodischer Neustart der WebEngine |
| ChromaDB-Konflikt wenn User es separat installiert | NIEDRIG | NIEDRIG | Keine ChromaDB-Nutzung (Entscheidung B.3) |
| PyInstaller-Kompatibilität mit WebEngine | NIEDRIG | HOCH | Frühzeitig testen (Phase 0) |
| VRAM-Druck durch Chromium + SigLIP gleichzeitig | MITTEL | MITTEL | QWebEngine nutzt System-RAM, nicht VRAM |
| Thread-Deadlock zwischen Graph-Build und UI | NIEDRIG | HOCH | Separater QThread für Graph-Operationen |

---

## Teil E: Abgrenzung — Was wird NICHT umgesetzt

Die folgenden Konzept-Elemente werden im MVP bewusst ausgelassen:

| Element | Grund | Spätere Phase? |
|---|---|---|
| GNN-basierte Summarization (GraphVSum) | Erfordert trainierte GNN-Modelle, Forschungsaufwand | Phase 2+ |
| Trainierte Projektionsnetzwerke (Audio↔Video) | Training-Daten und GPU-Zeit nötig | Phase 2+ |
| DR-DSN RL-Agent (Zhou et al.) | PyTorch RL-Training auf 6GB GTX 1060 nicht praktikabel | Phase 2+ |
| Write-A-Video Dynamic Programming | Eigenes Forschungsprojekt, >30 Tage Aufwand | Phase 3+ |
| DirectML ONNX-MatMul-Graph | Nicht relevant (NVIDIA statt AMD) | N/A |
| Sigma.js Migration | Nur wenn vis.js bei >5K Knoten versagt | Bei Bedarf |
| igraph Betweenness Centrality | NetworkX reicht für ≤5K Knoten | Bei Bedarf |

---

## Teil F: Dependency-Kompatibilitätsmatrix

Alle Pakete gegen bestehende Dependencies geprüft:

| Neues Paket | Version | Konflikte? | Geprüft gegen |
|---|---|---|---|
| networkx | 3.6.1 | ✅ KEINE | numpy, scipy (bereits installiert) |
| igraph | 1.0.0 | ✅ KEINE | Pure C + Python Binding |
| PySide6-WebEngine | 6.11.0 | ⚠️ Muss PySide6-Version matchen | PySide6==6.11.0 (prüfen!) |
| usearch | 2.23.0 | ✅ KEINE | numpy (bereits installiert) |
| vis-network | 9.1.9 | ✅ KEINE | Standalone JS, kein npm nötig |

**Kritischer Check:** PySide6-WebEngine MUSS exakt die gleiche Version wie PySide6 haben. Wenn PB Studio PySide6==6.7.x nutzt, muss PySide6-WebEngine==6.7.x installiert werden, NICHT 6.11.0.

**Aktion:** `pip show PySide6` ausführen und Version notieren → PySide6-WebEngine mit identischer Version installieren.

---

## Teil G: Checkliste zur Abarbeitung

### Sprint 1 (Tag 1–5): Foundation
- [ ] `pip show PySide6` → Version notieren
- [ ] `pip install networkx[default]==3.6.1 igraph==1.0.0`
- [ ] `pip install PySide6-WebEngine=={PYSIDE6_VERSION}`
- [ ] vis-network.min.js + .css herunterladen nach `resources/graph/`
- [ ] `services/graph_service.py` erstellen (Klasse + Singleton)
- [ ] `_compute_knn_edges()` implementieren (NumPy Brute-Force)
- [ ] `build_video_similarity_graph()` implementieren
- [ ] `get_vis_js_data()` implementieren
- [ ] `services/graph_persistence.py` erstellen
- [ ] Unit-Tests: `test_graph_build_*`, `test_knn_*`

### Sprint 2 (Tag 6–10): UI & Bridge
- [ ] `resources/graph/graph_viewer.html` erstellen
- [ ] vis.js Konfiguration (Barnes-Hut, Clustering, Farben)
- [ ] QWebChannel-Integration in HTML
- [ ] `services/graph_bridge.py` erstellen (GraphBridge QObject)
- [ ] GraphPanel Widget erstellen
- [ ] In Hauptfenster als Tab/DockWidget einbinden
- [ ] Klick-Events testen (Knoten → Video-Preview)
- [ ] Settings-Erweiterung in `settings_store.py`
- [ ] Integrations-Test: Graph-Panel öffnet und zeigt Daten

### Sprint 3 (Tag 11–15): Pacing-Integration
- [ ] `services/graph_pacing_integration.py` erstellen
- [ ] `is_repetition_safe()` implementieren
- [ ] Anti-Repetitions-Filter in `_match_video_for_segment()` einbauen
- [ ] `compute_graph_reward()` implementieren
- [ ] AdvancedPacingSettings erweitern
- [ ] `build_full_graph()` mit allen 4 Knotentypen implementieren
- [ ] 5 Kantentypen implementieren
- [ ] `set_project()` in session.py erweitern (Singleton-Reset)
- [ ] Migrations-Script für `graph_cluster_id` in scenes
- [ ] Integrations-Test: Auto-Edit mit Graph-Diversität

### Sprint 4 (Tag 16–20+): Polish, Testing, Deployment
- [ ] Performance-Tests (100, 1.000, 5.000 Clips)
- [ ] QWebEngineView GPU-Rendering testen
- [ ] Software-Rendering-Fallback als Setting
- [ ] PyInstaller `.spec` anpassen
- [ ] Test-Build erstellen
- [ ] NSIS-Installer testen
- [ ] Edge-Cases: leeres Projekt, 1 Clip, Projekt-Switch
- [ ] Memory-Profiling (RAM-Verbrauch über 1h Nutzung)
- [ ] Dokumentation aktualisieren

---

## Teil H: Metriken für Erfolg

Der Graph ist erfolgreich implementiert wenn:

1. **Funktional:** Ein Projekt mit 100+ Video-Clips zeigt einen interaktiven Graphen mit erkennbaren Clustern
2. **Performance:** Graph-Aufbau für 1.000 Clips dauert <2 Sekunden
3. **Anti-Repetition:** Auto-Edit mit Graph produziert messbar weniger Clip-Wiederholungen als ohne Graph (A/B-Test: Repetition-Rate sinkt um >30%)
4. **Stabilität:** Kein Crash bei Projekt-Switch, Clip-Löschen, oder langem Betrieb (>2h)
5. **Installer:** PyInstaller-Build funktioniert mit WebEngine auf sauberer Windows 11 Installation
