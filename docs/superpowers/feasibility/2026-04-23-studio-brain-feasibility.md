# Studio Brain — Machbarkeitsstudie

**Datum:** 2026-04-23
**Projekt:** PB Studio Rebuild
**Pipeline-Phase:** 4 (Feasibility)
**Inputs:** Design-Doc Phase 1, Research-Doc Phase 2, PRD Phase 3
**Output:** Go/No-Go-Entscheidung + Bedingungen für Phase 5 (Plan)

---

## 1. Technische Machbarkeit

### 1.1 Was bereits existiert (keine Neuentwicklung nötig)

Alle Bausteine, auf denen das Studio Brain aufbaut, sind vorhanden und produktionsreif:

| Komponente | Datei / Zeile | Verifizierter Zustand |
|---|---|---|
| SQLite mit WAL-Mode | `database/session.py:129` (`PRAGMA journal_mode=WAL`) | Aktiv — konkurrente Reads + 1 Writer sicher |
| Alembic-Migrations-Infrastruktur | `alembic.ini`, `database/alembic/versions/` | 3 bestehende Migrationen, funktionierend |
| SigLIP-Embedding-Cache (1152-dim) | `services/vector_db_service.py:24,64-80,193-198` | In-Memory-Cache-Matrix mit thread-safe Invalidierung — **direkt wiederverwendbar für Compat-Graph-Builder** |
| Scene-Model mit ai_caption/ai_mood/ai_tags | `database/models.py:119-141` | JSON-Felder, Schema kompatibel |
| Bestehende `AIPacingMemory` | `database/models.py:263-300` | Vorläufer — siehe Migrationsstrategie unten |
| `StructureSegment` mit is_dj_mix-Flag | `database/models.py:302` | Audio-Segmentierung vorhanden |
| `Beatgrid` mit energy_per_beat, onset-Daten | `database/models.py:143` | voll-analysierter Kontext verfügbar |
| `AnalysisStatus`-Registry | `services/analysis_status_service.py:24,35,175` | Bewährtes Pattern `VIDEO_STEPS` / `AUDIO_STEPS`-Listen — **Erweiterung um `structure_enrichment` ist 1-Zeilen-Add** |
| `scikit-learn 1.8.0` mit HDBSCAN | `requirements.txt:98` | `sklearn.cluster.HDBSCAN` verfügbar, keine neue Dep nötig |
| 9-stufige Audio-Pipeline (Genre/Key/Structure/etc.) | diverse `services/*_service.py` | alle Outputs im Snapshot nutzbar |
| 8-stufige Video-Pipeline (Scenes/Motion/Embedding/Caption) | `services/video_analysis_service.py` | Enrichment-Input vollständig |
| GPU-Model-Manager (Thread-Safe) | `services/model_manager.py` | Wir brauchen ihn nicht — Enrichment ist CPU-only |
| PySide6-UI-Stack inkl. Controllers/Widgets | `ui/` | `media_grid.py` / `media_table.py` als Pattern-Vorlagen |

**Kernaussage:** Es existiert keine Lücke, bei der grundlegende Infrastruktur neu gebaut werden müsste. Das Studio Brain ist eine **Verdichtungs- und Persistenz-Schicht über bereits vorhandener Analyse**.

### 1.2 Was neu gebaut werden muss

**Datenbank (3 Alembic-Migrationen):**

- `add_struct_layer_tables` — `struct_clip_tags`, `struct_style_bucket`, `struct_compat_edge`
- `add_memory_layer_tables` — `mem_pacing_run`, `mem_decision`, `mem_learned_pattern`, `mem_user_feedback_event`
- `extend_analysis_status_enum` — Registry-Update

**Neue Python-Module (Backend):**

| Modul | Aufwand-Schätzung | Abhängigkeiten |
|---|---|---|
| `services/brain_service.py` | M (aggregierte Read-Views, Cache) | SQLAlchemy, LRU-Cache |
| `services/backup_service.py` | S (DB-Copy + Rolling-Window) | shutil, os |
| `workers/structure_enrichment.py` | L (orchestriert 4 Schritte + Worker-Signals) | SQLAlchemy, Qt-Signals |
| `workers/memory_updater.py` | M (async Pattern-Aggregation) | SQLAlchemy, Qt-Threads |
| `services/enrichment/role_classifier.py` | S (pure Regelbaum aus YAML) | PyYAML, NumPy |
| `services/enrichment/mood_anchor_matcher.py` | S (Cosine gegen 10 Anchors) | NumPy, existierender SigLIP-Text-Encoder |
| `services/enrichment/style_bucket_clusterer.py` | M (UMAP + HDBSCAN + Reducer-Persistierung) | `umap-learn`, sklearn |
| `services/enrichment/compat_graph_builder.py` | S (Top-K auf Cache-Matrix) | NumPy |
| `services/pacing/scorer.py` | L (10+ Terme, vektorisiert) | NumPy |
| `services/pacing/variations_budget.py` | S (Sliding-Window-Zähler) | — |
| `services/pacing/pattern_aggregator.py` | M (Wilson + Context-Fingerprint-Aggregation) | NumPy |
| `services/pacing/decision_recorder.py` | S (denormalisierter Snapshot-Insert) | SQLAlchemy |
| `services/stats/wilson_lower_bound.py` | XS (pure Funktion) | math |

**Neue Python-Module (UI):**

| Modul | Aufwand-Schätzung |
|---|---|
| `ui/studio_brain_window.py` (Fenster + Tab-Switcher + QSettings) | L |
| `ui/studio_brain/structure_tab.py` (Graph+Grid+Filter+Inspector) | XL |
| `ui/studio_brain/memory_tab.py` (Timeline + Pattern-Tabelle) | M |
| `ui/studio_brain/audit_tab.py` (Segment-Strip + Cut-Tabelle + Term-Contributions) | L |
| `ui/studio_brain/steer_tab.py` (Pins/Excludes/Boosts) | M |
| `ui/story_map_dialog.py` | M |
| Integration Feedback-Shortcuts in Timeline-Controller (Edit) | S |

**Modifikationen bestehender Module:**

- `agents/pacing_agent.py` — **große Umstrukturierung**: heute LLM-gesteuert mit `base_cut_rate` / `energy_reactivity` (siehe `:104-108, :399-427`); die neue 4-stufige Pipeline muss hinzu, ohne die bestehende LLM-Natural-Language-Schicht zu zerstören (das ist eine bewusste UX-Komponente, siehe User-Memory „Keine Abkürzungen"). **Entkopplung nötig:** die LLM-Schicht übersetzt User-Wünsche in Weights-Profile-Overrides, die eigentliche Entscheidungs-Pipeline ist getrennt. Aufwand: L, mit Risiko (siehe Risiko R3).
- `services/onset_rhythm_service.py` — Per-Segment-Chunking ergänzen. Aufwand: M.
- `services/analysis_status_service.py` — Registry-Update (`VIDEO_STEPS` Line 24). Aufwand: XS.

**Neue Konfigurations-Dateien:**

- `config/enrichment_rules.yaml`
- `config/pacing_rules.yaml`
- `config/pacing_weights/{default,psytrance,house,dj_mix_auto}.yaml`
- `config/mood_anchors_v1.yaml` + generiertes `config/mood_anchors.npz`

**Tests:**

- Siehe Sektion 5 dieser Studie.

### 1.3 Zeit-Schätzung (grob, Plan-Phase verfeinert)

Nach T-Shirt-Größen gruppiert:

| Kategorie | XS | S | M | L | XL |
|---|---|---|---|---|---|
| Backend | 1 | 6 | 4 | 3 | 0 |
| UI | 0 | 1 | 2 | 2 | 1 |
| Tests | 0 | ~12 | ~5 | ~2 | 0 |

Mit typischen XS=2 h, S=4 h, M=8 h, L=16 h, XL=32 h ergibt das **ca. 240-300 Stunden** Solo-Entwicklungsaufwand (inkl. Tests, Doku, Polish). Bei 4 Stunden/Tag fokussierter Arbeit = **12-15 Wochen**. Diese Zahl ist **nicht** Teil der Machbarkeits-Bedingungen, nur zur Skalierungs-Einschätzung.

### 1.4 Breaking Changes in bestehender Code-Basis

**Keine.** Alle Änderungen sind additiv oder abwärtskompatibel:

- Neue DB-Tabellen (FK zu bestehenden, `ON DELETE CASCADE` nur wo sinnvoll).
- Neue `AnalysisStatus`-Registry-Einträge (bestehende Einträge unverändert).
- Neue Dependencies (keine Entfernung).
- `pacing_agent.py`-Refactoring ist intern; öffentliches Interface (Worker-Signals) bleibt.
- `onset_rhythm_service.py`-Erweiterung ist backward-compatible (Default-Pfad unverändert bei fehlendem `structure_segments`-Parameter).

**Offene Frage:** `AIPacingMemory` (bestehend) vs. neue `mem_learned_pattern`. Drei Optionen:

1. **Coexist, Deprecate, Migrate später.** Neue Pipeline nutzt nur `mem_*`. `AIPacingMemory` wird beim ersten Studio-Brain-Enable ausgelesen und best-effort in `mem_learned_pattern` übernommen (falls vorhandene Daten vorhanden sind). Tabelle bleibt im Schema als Legacy.
2. **Hard Deprecation.** Alembic-Migration löscht `AIPacingMemory` nach Migration der Daten. Schlanker, aber riskant bei nicht antizipierten Lesepfaden.
3. **Als Alias beibehalten.** `AIPacingMemory` wird zu View auf `mem_learned_pattern`.

**Empfehlung:** Option 1 — konservativ, nachbesserbar. Ab Plan-Phase entscheiden.

---

## 2. Ressourcen

### 2.1 VRAM-Budget (GTX 1060, 6 GB)

**Kritischer Punkt.** Die bestehende Pipeline belegt VRAM bereits intensiv:

| Consumer | Peak-VRAM (geschätzt) | Konkurrent zu |
|---|---|---|
| SigLIP (video_analysis) | ~1.5 GB | Gemma |
| RAFT Optical Flow | ~1.0 GB | SigLIP |
| Gemma Vision Caption | ~3.5 GB (via Ollama/Transformers) | SigLIP, RAFT |
| DEMUCS Stem-Separation | ~1.8 GB (chunked 30s) | beat_this |
| beat_this Beat-Detection | ~0.8 GB (chunked 10 min) | — |

**Studio-Brain-Beitrag zum VRAM: 0 GB.** Alle Enrichment-Schritte laufen ausschließlich auf CPU — das ist im Design bewusst so gewählt und wird in Machbarkeit bestätigt:

- `RoleClassifier`: pure Python/NumPy
- `MoodAnchorMatcher`: NumPy-Cosine (Text-Anchor-Embeddings werden **einmalig** offline erstellt — da braucht man kurz GPU-Zeit, aber das ist Setup, nicht Runtime)
- `StyleBucketClusterer`: UMAP + HDBSCAN, beide scikit-learn-CPU
- `CompatGraphBuilder`: NumPy-Matrix-Operation auf Cache
- `PacingScorer`: NumPy-Matrix
- `PatternAggregator`: SQLite-Queries + NumPy

**Einmalige GPU-Nutzung beim Setup:** Generierung der `mood_anchors.npz` — erfordert SigLIP-Text-Encoder-Call für 10 Prompts. ~5 s Einmal-Operation bei Installation / Config-Update.

**Verdikt:** ✅ VRAM-machbar. Keine Konkurrenz zur bestehenden Pipeline.

### 2.2 RAM-Budget (System-RAM)

Kritisch für 1–3h-DJ-Mix-Verarbeitung. PRD-Ziel: ≤ 2 GB Peak.

| Komponente | RAM-Schätzung | Quelle |
|---|---|---|
| librosa.load(3h, 22050 Hz, mono, float32) | ~950 MB | (3·3600·22050·4)/2²⁰ |
| SigLIP-Cache-Matrix (5000 Scenes × 1152 × 4B) | ~23 MB | verifizierter Cache-Mechanismus |
| UMAP-Reducer in-memory | ~50–150 MB | abhängig von n_neighbors und Datensatz |
| HDBSCAN-Baum | ~30–80 MB | minimal |
| Scoring-NumPy-Matrizen (pro Run, 500 Kandidaten × 13 Terme) | ~0.5 MB | vernachlässigbar |
| Pacing-Agent-LRU-Cache (256 Context-Fingerprints) | ~2 MB | vernachlässigbar |
| PySide6-Fenster inkl. Graph-Rendering (1000 Knoten) | ~100-300 MB | Qt-Standard |
| **Peak (3h DJ-Mix + Enrichment + UI offen)** | **~1.5-1.7 GB** | **Unter Budget** |

**Verdikt:** ✅ RAM-machbar mit Puffer. Einzige Gefahr: wenn `onset_rhythm_service` beim DJ-Mix-Chunking versehentlich doppelt lädt — muss im Code-Review in Phase 5 geprüft werden.

### 2.3 CPU-Budget

**Enrichment-Worker:**

- 1000 Scenes: ~12 s
- 5000 Scenes: ~80 s (PRD-Ziel ✅)
- 10000 Scenes: ~180 s (akzeptabel, im Worker, UI mit Progress)

**Re-Clustering-Trigger** (bei ≥ 50 neuen Clips):

- UMAP-Fit: skaliert O(N × n_neighbors); 5000 Scenes × 30 ≈ 150k Operationen → ~3–10 s
- HDBSCAN: schneller auf reduzierten Daten, ~1–5 s
- Zusammen unter 30 s, sollte im Hintergrund-Worker laufen

**Pacing-Agent-Scoring:**

- Ziel: ≤ 20 ms pro Cut (500 Kandidaten, 13 Terme)
- NumPy-Matrix-Multiplikation `W @ features.T`: O(K × T × N) = 500 × 13 × 1 ≈ 6500 Ops → deutlich unter 1 ms
- SQLite-Lookups für `historical_accept_rate`: LRU-gecacht, typisch 256 unique Fingerprints pro Run; erste Abfrage ~5 ms, Cache-Hit < 0.1 ms
- **Realistisches Budget:** 5-15 ms pro Cut. ✅

**Feedback-Keystroke-Latenz:**

- Ziel: ≤ 100 ms
- SQLite-Insert in separatem Thread: ~10-30 ms Commit-Latenz
- Qt-Signal-Roundtrip: < 5 ms
- **Realistisches Budget:** ~20-50 ms. ✅

### 2.4 Disk-Budget

Bereits in Design-Doc Sektion 8.6 verifiziert: **~14 MB für 5000 Scenes + 50 Runs**. Vernachlässigbar.

**Backup-Policy:** 14 rolling Backups × ~100 MB (volle DB) = 1.4 GB Disk max. Für `storage/backups/`-Ordner reservieren.

**Zusätzlicher Disk-Bedarf:**

- `storage/enricher/umap_v1.pkl` — UMAP-Reducer, ~50 MB
- `config/mood_anchors.npz` — 10 × 1152 × 4B = ~46 KB
- Style-Bucket-Centroide in DB: 12 × 1152 × 4B × 2 (numpy overhead) = ~110 KB

**Verdikt:** ✅ Disk-machbar mit reichlich Puffer.

### 2.5 Laufzeit-Kosten

- **Nur lokale Operationen** — keine Cloud-Calls, keine API-Kosten.
- Einzig mögliche Netzwerk-Operation: Mood-Anchor-Generierung beim Setup, falls `siglip`-Modell nicht lokal vorhanden. Einmal ~5 MB Download.

---

## 3. Risiken

**Top 5, priorisiert nach Likelihood × Impact.** Jedes Risiko hat eine Mitigation oder ein Abbruchkriterium.

### R1 — Mood-Anchor-Qualität unzureichend (hoch × mittel)

**Risiko:** Die 10 SigLIP-Text-Anker sind unbenchmarked (siehe Research W2). Paarweise Similarity ≥ 0.5 würde heißen, dass zwei Mood-Klassen sich überlappen und die Klassifikation inkonsistent wird.

**Likelihood:** hoch (ohne empirische Kalibrierung)
**Impact:** mittel (Mood-refined wird unbrauchbar, aber Role/Style/Compat-Graph funktionieren unabhängig — der Agent verliert nur den Mood-Term, das System nicht)

**Mitigation:**

- Akzeptanz-Kriterium (Test `test_mood_anchor_orthogonality.py`): paarweise Cosine-Similarity < 0.5 für alle 10 Anchors. Wenn Test fehlschlägt, müssen Prompts ausgetauscht werden.
- Bei anhaltendem Fehlschlag: Fallback auf die bestehenden 4-Klassen `ai_mood` von Gemma, Mood-Term-Gewicht auf 0 setzen.
- Progressive Verfeinerung: User kann in `config/mood_anchors_v1.yaml` eigene Prompts einsetzen; System erlaubt mehrere `vN`-Versionen parallel.

**Abbruchkriterium:** **Nein.** Mood-Qualität ist nicht geschäftskritisch — wenn nicht lösbar, wird Mood-Refinement in Phase 2 verschoben; Rest des Features bleibt wertvoll.

### R2 — Onset-Chunk-Boundary-Artefakte bei DJ-Mixen (mittel × hoch)

**Risiko:** librosa hat keine offizielle Chunk-Strategie (Research W1). Unser Per-Segment-Pattern kann an Segment-Grenzen doppelt oder zu wenig Onsets erkennen. Bei 3h-Mix mit ~30-50 Segment-Grenzen sind fehlerhafte Onsets auf 30-50 Stellen gestreut — kann Beat-Grid verschieben, was Pacing durcheinander bringt.

**Likelihood:** mittel (Research zeigt dokumentierte Fallen, Implementierung muss sorgfältig sein)
**Impact:** hoch (wenn Beat-Grid kippt, kollabiert die gesamte Pacing-Logik für diesen Mix)

**Mitigation:**

- `test_onset_chunked_boundary.py` als harte Test-Bedingung (Boundary-Overlap-Test, synthetisches Onset genau auf Grenze).
- Referenz-Vergleich: bei 30-min-Mix (innerhalb MAX_DURATION_SEC) Ergebnisse von Chunked vs. Single-Pass müssen identisch sein (± 1 Frame).
- Zusätzlich: `test_dj_mix_3h.py` Regression gegen kuratierten Golden-Mix mit manuell verifizierten Onsets.

**Abbruchkriterium:** **Ja.** Wenn die Tests auch nach Plan-Phase-Implementation nicht grün werden, ist DJ-Mix-Support > 30 min nicht Release-bereit und muss als „beta"-Feature gekennzeichnet werden oder zurückgestellt werden.

### R3 — LLM-Pacing-Layer-Kollision (mittel × mittel)

**Risiko:** Der bestehende `agents/pacing_agent.py` hat eine LLM-gesteuerte Natural-Language-Schicht (siehe `:104-108, :399-427`), die `base_cut_rate`, `energy_reactivity`, `breakdown_behavior` aus User-Text ableitet. Die neue 4-stufige Pipeline (Hard-Rules / Budget / Kollision / Scoring) darf diese Schicht nicht zerstören — der User will weiterhin „schnelle Schnitte, hohe Energie" als Text eingeben können.

**Likelihood:** mittel (Refactoring ist nichttrivial; Parameter-Mapping nicht 1:1)
**Impact:** mittel (verliert ein UX-Feature, aber Kern-Pacing bleibt funktionsfähig)

**Mitigation:**

- Klare Entkopplung: die LLM-Schicht bleibt als **Profile-Override-Layer**. Natural-Language-Input produziert **keine Scoring-Parameter direkt**, sondern ein ad-hoc `pacing_weights/_tmp.yaml`, das in die Scoring-Pipeline fließt. Bestehende Parameter werden auf die neue Term-Formel abgebildet (z. B. `energy_reactivity=80%` → `w_energy` +50 %).
- Integration-Test: bestehende LLM-Examples aus `pacing_agent.py:402-404` müssen nach Refactoring noch sinnvolle Pacing-Runs erzeugen.
- Prior-Art: die Weights-YAML-Struktur akzeptiert partielle Overrides (inherits from `default.yaml`), daher ist `_tmp.yaml` unkritisch.

**Abbruchkriterium:** **Nein.** Fällt im Notfall als Polish-Feature aus; die neue Scoring-Pipeline ist unabhängig einsetzbar.

### R4 — UMAP-Reducer-Versions-Drift (mittel × mittel)

**Risiko:** Ein UMAP-Reducer muss persistiert (pickle) werden und darf sich bei neuen Clips nicht unvorhersehbar verändern. Re-Fit bei ≥ 50 neuen Clips (Design-Default) könnte bestehende Style-Bucket-IDs verschieben — historische `mem_decision.clip_style_bucket_id` zeigen dann auf einen alten Cluster, der nach Re-Fit nicht mehr existiert oder eine andere Bedeutung hat.

**Likelihood:** mittel (tritt zwangsläufig bei wachsenden Libraries auf)
**Impact:** mittel (Gedächtnis-Patterns werden partiell ungültig, Lernkurve hiccup)

**Mitigation:**

- **`enricher_version` strikt durchhalten** — jede Style-Bucket-Zeile trägt Version; bei Version-Wechsel werden neue Buckets **zusätzlich** erzeugt, alte bleiben bis alle referenzierenden Decisions alt sind.
- `struct_style_bucket` muss eine `active=BOOLEAN`-Spalte bekommen (Design muss in Plan-Phase ergänzt werden), damit UI nur aktive Buckets zeigt, Decisions aber auf alte verweisen können.
- `mem_decision.at_enricher_version` speichern, um Snapshot rückwärts-kompatibel zu halten.
- Pattern-Re-Aggregation ignoriert Decisions mit veralteter Enricher-Version (oder aggregiert separat pro Version, falls das wertvoll ist).

**Abbruchkriterium:** **Nein.** Ist ein Design-Detail, das in der Plan-Phase glattgezogen wird.

### R5 — Force-Directed-Layout bei > 2000 Knoten zäh (niedrig × niedrig)

**Risiko:** Bei großen Libraries (> 2000 Scenes) könnte das Graph-View zu lahm werden, auch mit vorberechnetem Layout (Qt-Rendering von 2000 QGraphicsItems + 40k Kanten).

**Likelihood:** niedrig (typische Libraries sind 500-2000, der User hat keine konkrete Zielgröße > 5000 genannt)
**Impact:** niedrig (UI-Fallback auf Grid-Only ist einfach möglich)

**Mitigation:**

- Auto-Fallback: Graph-Mode wird deaktiviert, wenn Scene-Anzahl > 2000 (Konfig-Schwelle). Grid-Mode bleibt funktional.
- Graph-Sampling: Optional nur Top-K-Verbundene anzeigen (ausblenden des long tail).
- Compat-Edges nur für Top-5 Nachbarn rendern (statt Top-20), reduziert Kantenzahl drastisch.

**Abbruchkriterium:** **Nein.** Kann in Phase 5 oder später nachgebessert werden.

### Zusätzliche Risiken (nicht Top-5, aber erwähnenswert)

- **R6** — Wilson bei 0/0: Code-Detail, in Plan dokumentiert (Fallback 0.5).
- **R7** — Steer-Override-State nach Crash: `steer_overrides`-Tabelle ist run-scoped; Crash zwischen „Start Run" und „Decision-Writing" könnte verwaiste Steer-Snapshots hinterlassen. Cleanup bei App-Start prüfen.
- **R8** — DB-Locking bei parallel laufendem Enrichment + Pacing-Run: SQLite-WAL erlaubt konkurrente Reads, aber zwei Writer sind serialisiert. Enrichment läuft im Worker, Decision-Writer ebenfalls. Lock-Contention möglich bei sehr schnellem Cut-Rate; Retry-Strategie im `DecisionRecorder` entschärft das.

---

## 4. Dependencies & Integrationen

### 4.1 Neue Python-Dependencies

| Paket | Version | Lizenz | Größe | Zweck |
|---|---|---|---|---|
| `umap-learn` | >= 0.5 | BSD-3 | ~1.5 MB | Style-Bucket-Preprocessing |
| `pyqtgraph` | >= 0.13 | MIT | ~1 MB | Tension-Kurve, Segment-Strip, Story-Map |
| `networkx` | >= 3.0 | BSD-3 | ~2 MB | Force-Directed-Layout offline |

**Alle drei lizenzkompatibel** mit dem bestehenden Stack (siehe `THIRD_PARTY_LICENSES.txt`). Keine Build-Chain-Komplexität (alle pure Python oder reine NumPy-Wrapper, keine Native-Kompilation).

**Indirekte Dependencies:** UMAP zieht `numba`, `pynndescent` als Sub-Deps. Alle BSD/MIT, bereits in wissenschaftlichem Python-Ökosystem etabliert.

### 4.2 Bereits vorhandene Dependencies (werden konsumiert)

- `scikit-learn==1.8.0` → `sklearn.cluster.HDBSCAN`
- `alembic==1.15.1` → Migrationen
- `numpy`, `scipy` (via scikit-learn)
- `PySide6` (kompletter UI-Stack)
- `SQLAlchemy` + SQLite-WAL

### 4.3 Berührte bestehende Services (Integration-Points)

| Service | Integration | Art |
|---|---|---|
| `services/video_analysis_service.py` | Enrichment läuft **nach** `scene_db_storage` | append (neuer Worker-Trigger) |
| `services/vector_db_service.py` | Enrichment nutzt den bestehenden `_cache_matrix` | read-only |
| `services/analysis_status_service.py` | Neuer Step `structure_enrichment` in `VIDEO_STEPS` | 1-Zeilen-Add |
| `services/onset_rhythm_service.py` | Erweiterung um Per-Segment-Chunking | Parameter-Add (backward-compat) |
| `services/pacing_service.py` | Neues Scoring-Backend | internes Refactoring |
| `services/model_manager.py` | **keine** Berührung (Enrichment ist CPU-only) | — |
| `services/knowledge_loader.py` | **keine** Berührung (globale LLM-Kontext, unabhängig vom Studio-Brain-Memory) | — |
| `agents/pacing_agent.py` | LLM-NL-Layer bleibt + neue Scoring-Pipeline | Koexistenz |
| `ui/clip_inspector.py` | ggf. Erweiterung um Studio-Brain-Tags | optional |
| `ui/controllers/media_table.py` | **keine** Berührung | — |

### 4.4 Berührte Datenbank-Tabellen

- **Read-Only zugegriffen:** `scene`, `video_clip`, `audio_track`, `beatgrid`, `structure_segment`, `analysis_status`
- **Neu erstellt:** 7 Tabellen (`struct_*` × 3, `mem_*` × 4)
- **Modifiziert:** keine (Additiv)
- **Konflikt mit bestehender `AIPacingMemory`:** siehe Sektion 1.4 Option 1.

### 4.5 Config-Integration

Alle neuen Configs in `config/`-Unterordner. Kein Konflikt mit bestehenden `config/`-Dateien. Pfadkonvention: `config/<domain>/<file>.yaml` (neues Unterordner-Pattern für Weights-Profile).

### 4.6 Python-Version-Kompatibilität

Projekt nutzt Python 3.10 (verifiziert via `requirements-py310-cu113.txt`). Alle neuen Deps sind 3.10-kompatibel.

---

## 5. Test-Strategie

### 5.1 Was ist testbar VOR Implementation?

**Komponenten, die isoliert getestet werden können:**

- **RoleClassifier** — synthetische (motion, duration, tags)-Tupel mit erwarteten Outputs. Test vor Produktivdaten.
- **WilsonLowerBound** — pure Funktion, mathematisch verifizierbar gegen Referenz-Werte.
- **VariationsBudget** — synthetische Cut-Sequenz, erwartete Counter-States.
- **PatternAggregator** — synthetische Decision-Sets mit erwarteten Pattern-Outputs.
- **CompatGraphBuilder** — synthetische Embedding-Cluster, Top-K-Korrektheit prüfbar.

**Komponenten, die Fixture-Daten benötigen:**

- **MoodAnchorMatcher** — echte SigLIP-Text-Embeddings für die 10 Prompts (Setup-Schritt im Test).
- **StyleBucketClusterer** — mindestens 30 synthetische oder aus bestehender DB gezogene Embeddings, um HDBSCAN stabil zu prüfen.
- **PacingScorer** — Mock-Context mit allen Audio-Kontext-Feldern, Mock-Clips, erwartete Score-Ordnung.

**Komponenten, die Integration-Tests brauchen:**

- **Full Enrichment Pipeline** — 20-Clip-Fixture in `tests/fixtures/clips/`, kompletter Run, Zieltabellen-Assertion.
- **Pacing mit Memory** — zwei aufeinander-folgende Runs, Pattern-Influence-Nachweis.
- **DJ-Mix-3h** — synthetischer 3h-Audio (Sinus-Kette mit bekannten Structure-Grenzen), End-to-End.
- **Alembic Up/Down Roundtrip** — gegen leere und gefüllte Test-DB.

**UI-Tests (offscreen):**

- Fenster öffnet, 4 Tabs rendern ohne Crash.
- Feedback-Shortcuts erzeugen `mem_user_feedback_event` korrekt.

**Golden-Run-Snapshot-Test:**

- Kuratierter 5-min-Test-Mix + 20-Clip-Library → `mem_decision`-Output byte-identisch (modulo Timestamps) über PRs.

### 5.2 Test-Daten-Anforderungen

| Testdaten-Set | Größe | Herkunft |
|---|---|---|
| 20-Clip-Fixture | 20 Scenes, gemischte Rollen/Moods | aus existierender User-Library ziehen, anonymisieren (Metadata nur) |
| 10 Mood-Anchor-Embeddings | 10 × 1152 float32 | einmalig via SigLIP-Text-Encoder generiert |
| Synthetischer 3h-Audio | WAV, 22050 Hz, mono, mit markierten Segment-Grenzen | `scripts/generate_test_dj_mix.py` (schreibbar in Plan-Phase) |
| 5-min-Golden-Mix | kuratierter realer Mix + 20-Clip-Paar | einmal kuratiert vom User, fixed für Regressions-Tests |

**Kritischer Fixture-Aufwand:** Der Golden-Mix muss vom User selbst bereitgestellt oder kuratiert werden. Das ist kein Blocker, aber eine Input-Abhängigkeit im Plan.

### 5.3 Prior Art in bestehendem Test-Stack

Projekt hat bereits:
- `tests/` mit Unit/Integration-Split
- Headless Qt-Test-Pattern (vermutet, muss in Plan geprüft werden)
- Pytest als Runner, pytest-cov für Coverage

**Empfohlener Standard für neue Tests:** `≥ 80 %` Coverage auf neuen Dateien, `mypy --strict` clean.

### 5.4 Akzeptanz-Kriterien (messbar, nicht nur „Tests grün")

- Alle Unit-Tests grün → `pytest tests/enrichment/ tests/pacing/ tests/memory/` Exit 0.
- Alle Integration-Tests grün → `pytest tests/integration/` Exit 0.
- `test_dj_mix_3h.py` RAM-Peak ≤ 2 GB (`memory_profiler`-Messung).
- `test_mood_anchor_orthogonality.py` alle paarweisen Similarities < 0.5.
- Golden-Run-Snapshot byte-identisch.
- UI-Offscreen-Tests grün.
- `mypy --strict` clean auf neuen Modulen.

---

## 6. Alternativen (Rückblick im Licht der Recherche)

Die Brainstorming-Phase hatte ursprünglich drei, dann vier Ansätze. Im Licht der Research bestätigen sich die Entscheidungen:

### Verworfene Ansätze — warum im Retrospect richtig

**A — Nur Struktur-Hirn.** Deckt „Erinnerungen aufbauen" nicht ab. Research W4 hätte für A keinen Nutzen gehabt (kein Gedächtnis → keine Wilson-Confidence nötig). User-Ziel nicht erreicht. ✅ korrekt verworfen.

**M — Nur Gedächtnis-Hirn.** Cold-Start-Problem: ohne Struktur-Tags kein aussagekräftiger Context-Fingerprint, also keine Pattern-Bildung in frühen Runs. Der Research-Finding „Wilson stabilisiert erst bei n≈10" hätte M in Runs 1-10 praktisch wertlos gemacht. ✅ korrekt verworfen.

**B — Obsidian-as-Viewer (external).** Research bestätigt indirekt: Obsidian-Graph ist für Similarity-Netze nicht out-of-the-box geeignet (Wikilinks ≠ Embedding-Edges), und der User hat App-Wechsel kategorisch abgelehnt. ✅ korrekt verworfen.

**C — Hybrid mit MD-Export zu Brain-Bug.** Research zeigt: Brain-Bug ist explizit als Dev-Vault definiert (CLAUDE.md), keine Vermischung mit App-Usage-Daten. User-Bestätigung: „nicht Teil des Entwicklungs-Hirns". ✅ korrekt verworfen.

### Gewählter Ansatz H — bestätigt

**H — Struktur + Gedächtnis in-app.** Research hat nichts hervorgebracht, was H in Frage stellt. Die einzigen Anpassungen sind Implementierungs-Details (UMAP-Preprocessing, Wilson-Parametrisierung, Onset-Chunking-Eigenbau). Die Architektur bleibt.

### Neue, durch Research aufgetauchte Alternativ-Fragen

- **SigLIP 1 vs SigLIP 2:** sofort migrieren oder nicht? → Feasibility-Empfehlung: **nicht jetzt**. Phase 1 nutzt vorhandene Embeddings (SigLIP 1, 1152-dim). Migration ist drop-in (gleiche Dim) und kann in v1.1 erfolgen, sobald Hauptfeature stabil ist.
- **k-means vs HDBSCAN:** k-means wäre deterministischer und schneller, erzwingt aber feste Cluster-Anzahl. Research bestätigt: HDBSCAN + UMAP ist bei heterogenen Embeddings deutlich besser (bis +60 % Accuracy). ✅ HDBSCAN bleibt.
- **PyQtGraph vs matplotlib vs QChart:** keine ist installiert; PyQtGraph ist Qt-nativ, schnell, MIT. ✅ PyQtGraph.
- **NodeGraphQt als fertige Graph-UI:** Research bestätigt als ungeeignet. ✅ Eigenbau mit QGraphicsScene.

---

## 7. Go / No-Go / Go-with-Conditions

### Empfehlung: **GO with Conditions**

Das Projekt ist technisch umsetzbar auf der verifizierten Infrastruktur (GTX 1060, 6 GB VRAM, SQLite WAL, scikit-learn 1.8, PySide6). Alle neuen Dependencies sind lizenzkompatibel und klein. Die Haupt-Risiken (Mood-Anchor-Qualität, Onset-Chunking-Artefakte, Pacing-Agent-LLM-Koexistenz) sind **lösbar mit klaren Tests und Mitigations**, keines ist ein struktureller Blocker.

### Bedingungen für den Übergang in Phase 5 (Plan)

1. **`AIPacingMemory`-Migration konkretisieren.** Option 1 (Coexist + best-effort-Import) als Default; explizite Migration-Strategie im Plan.

2. **`struct_style_bucket.active`-Spalte ergänzen** (im Design-Doc nicht explizit; kommt aus R4). Muss in die `add_struct_layer_tables`-Migration.

3. **`mem_decision.at_enricher_version` ergänzen.** Für R4-Mitigation zur Version-aware Snapshot-Erhaltung.

4. **Golden-Mix-Fixture vom User bereitstellen lassen** als Input für die Test-Implementation. Der User muss einen kleinen, reproduzierbaren 5-min-Test-Mix zusammen mit seinen 20 Fixture-Clips kuratieren. (Ist mit ihm im Plan zu klären.)

5. **`test_mood_anchor_orthogonality.py` blockiert Release, wenn rot.** Wenn Anchors nach Kalibrierung nicht orthogonal genug sind: Mood-Refinement wird auf v1.1 verschoben, `w_mood_*` wird auf 0 gesetzt, Ship ohne Mood-Term.

6. **`test_onset_chunked_boundary.py` blockiert DJ-Mix-Feature (> 30 min), wenn rot.** Wenn Artefakte nicht lösbar: DJ-Mix-Support wird als „beta" markiert oder zurückgestellt. Sub-1-h-Mixe müssen unabhängig funktionieren.

7. **Weights-Tuning-Fenster bleibt Konfig-basiert.** Kein User-Facing-Slider für die 13 Gewichte — das ist Entwickler-/Power-User-Interface. YAML-Editor-Integration (über Steer-Tab „Profil bearbeiten"-Button) reicht für Phase 1.

8. **Pacing-Agent-LLM-Layer-Refactoring als eigener Sub-PR.** Nicht in den Enrichment- oder Memory-Commits vermischen, weil Rollback-Pfade getrennt möglich bleiben müssen.

9. **Performance-Regression-Test im Plan.** Vor-/Nach-Release-Benchmark von Pacing-Agent-Latenz (Baseline vs. neu). Bei > 50 % Verlangsamung: Review.

10. **Feature-Flag NICHT nötig.** Wurde im Design abgelehnt; Feasibility bestätigt: additive Änderungen, kein Risiko für bestehende Funktionen, ein-Branch-Merge. Kein Flag-Overhead nötig.

### Was kein No-Go wäre

- **Wenn HDBSCAN instabil ist** → Fallback auf k-means mit fester Cluster-Anzahl (≈ 10).
- **Wenn UMAP-Reducer zu instabil** → UMAP überspringen, direkt HDBSCAN auf 1152-dim mit höherem `min_cluster_size`, Qualitäts-Einbußen akzeptieren für Phase 1.
- **Wenn Force-Directed-Layout zu langsam** → nur Grid-Mode anbieten, Graph-Mode in v1.1.
- **Wenn 3h-DJ-Mix-RAM-Budget überschritten wird** → Enrichment-Worker-Batching verbessern, oder 3h-Mixe in zwei 1.5h-Halbteile zerlegen.

### Was ein No-Go wäre (nicht eingetreten)

- WAL-Mode in SQLite nicht verfügbar → ist aktiv ✅
- SigLIP-Embedding-Dim unpassend → 1152 passt ✅
- scikit-learn-Version zu alt für HDBSCAN → 1.8.0 hat es ✅
- Alembic-Infrastruktur fehlt → existiert mit 3 bestehenden Migrations ✅
- User verlangt externe Obsidian-Integration trotz Aufwand → explizit abgelehnt ✅
- User verlangt GPU für Enrichment → Bedarf nicht da, CPU reicht ✅

---

## Zusammenfassung

| Kriterium | Status |
|---|---|
| Technisch machbar | ✅ |
| VRAM-Budget (GTX 1060, 6 GB) | ✅ (0 GB-Beitrag) |
| RAM-Budget (3h DJ-Mix ≤ 2 GB) | ✅ mit Puffer |
| CPU-Budget (Enrichment ≤ 80 s) | ✅ |
| Disk-Budget (Daten + Backups) | ✅ |
| Lizenzkompatible Deps | ✅ (alle MIT/BSD) |
| Bestehende Features unberührt | ✅ (additiv) |
| Risiken lösbar | ✅ (Mitigations dokumentiert) |
| Tests spezifizierbar | ✅ |
| User-Ziele gedeckt | ✅ (Qualität, Fehler-Vermeidung, Erinnerungen) |

**Verdikt: GO, unter den 10 Bedingungen in Sektion 7.**

Alle Bedingungen sind in Phase 5 (Plan) in konkrete Tasks zu überführen. Kein Blocker für Phase 5.
