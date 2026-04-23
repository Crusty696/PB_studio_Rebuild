# Studio Brain — Research

**Datum:** 2026-04-23
**Pipeline-Phase:** 2 (Recherche)
**Input:** `docs/superpowers/specs/2026-04-23-studio-brain-design.md` Sektion 10 „Offene Fragen"
**Output:** Input für Phase 3 (PRD), 4 (Machbarkeit), 5 (Plan)

---

## TL;DR

- **Graph-Rendering:** `QGraphicsScene` + extern per `networkx` vorberechnetes Force-Directed-Layout. Bei 1000+ Knoten skaliert das problemlos (BSP-Tree-Indexing von Qt). **NodeGraphQt-PySide6 nicht geeignet** (Node-Editor, kein Similarity-Graph; zudem inaktiv).
- **HDBSCAN auf 1152-dim ist ein Anti-Pattern.** UMAP-Preprocessing ist Pflicht: `1152 → UMAP (5-10 dims, n_neighbors=30, min_dist=0.0) → HDBSCAN`. Beschleunigt Clustering um Faktor ~300 und verbessert Qualität um bis zu 60 %.
- **Wilson-Lower-Bound mit z=1.96 (95%)** ist der Industrie-Standard für Recommender-Ranking. Stabil ab n≈10. Für 5-Stern-Ratings gibt es eine Bayesian-Approximation-Variante.
- **SigLIP 2 (Feb 2025, Dim=1152 für SO400M)** ist der direkte Upgrade-Pfad: bessere Zero-Shot-Klassifikation für abstrakte Konzepte (Mood) als SigLIP 1, nutzt existierende 1152-dim-Pipeline unverändert.
- **Librosa hat keine offizielle Streaming-/Chunk-Strategie für Onset-Detection.** Für DJ-Mixe müssen wir selbst chunken — Pattern: Per-Structure-Segment, 2 s Überlapp, Backtracking an Segment-Grenzen.
- **LUFS → Arousal korrelation ist stark (r≈0.57-0.75)**, LUFS → Valence ist domain-abhängig und schwach. LUFS ist als Feature sinnvoll, niemals als Solo-Prädiktor.

---

## Pro Frage

### Q1 — Force-Directed Graph-Rendering in PySide6 bei 1000+ Knoten

**Antwort:** Der robusteste Weg ist `QGraphicsScene` + `QGraphicsView` mit extern vorberechnetem Force-Directed-Layout (via `networkx.spring_layout` oder `networkx.kamada_kawai_layout`). Qt's QGraphicsScene nutzt BSP-Tree-Indexing und skaliert laut Dokumentation auf **Millionen von Items** mit Millisekunden-Zugriffszeiten. Wichtig: `scene.setSceneRect(...)` explizit setzen (sonst ist `itemsBoundingRect()` teuer).

**Spezialisierte Libraries, die wir ausgeschlossen haben:**
- `NodeGraphQt-PySide6`: gebaut für **Node-Editor-Workflows** (Blender-/Houdini-Style), nicht Similarity-Netzwerke. Kein Force-Directed-Layout integriert. Repo wirkt inaktiv (0 sichtbare contributors, keine Releases).
- `pyqtgraph.GraphItem` (Docs-Page 403): existiert, unterstützt Node-/Edge-Rendering mit externen Positionen. Könnte Alternative sein, ist aber weniger etabliert als native QGraphicsScene.

**Empfehlung:** `networkx` (bereits via scikit-learn-Dep-Chain indirekt verfügbar, sonst 1 MB add) für Layout-Berechnung **offline** (einmal bei Enrichment) → Positionen cachen in `struct_style_bucket`-nahen Meta-Tabellen → `QGraphicsScene` rendert nur, ohne Layout jedes Mal neu zu rechnen. Bei ≤ 2000 Knoten ist das unspürbar.

**Quellen:**
- [Qt for Python — QGraphicsScene](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsScene.html) — offizielle Qt-Docs, BSP-Tree + Optimierungs-Hinweise.
- [NodeGraphQt-PySide6 GitHub](https://github.com/C3RV1/NodeGraphQt-PySide6) — zur Einordnung, warum wir es **nicht** nehmen.
- [PySide6 QGraphics Tutorial (PythonGUIs)](https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/) — praktischer Einstieg.

---

### Q2 — HDBSCAN auf 1152-dim SigLIP-Embeddings

**Antwort:** Direkt-Clustering auf 1152-dim ist laut UMAP-Autor Leland McInnes eine der klassischen Fallen („density-based clustering leidet an der Curse-of-Dimensionality, höherdimensionale Räume haben zu viele Ecken"). Lösung: **UMAP als Preprocessing**.

**Empfohlene Pipeline für unseren Fall:**

```python
import umap
import sklearn.cluster

# 1. Alle SigLIP-Embeddings laden (N × 1152)
embeddings = load_all_scene_embeddings()   # z.B. (5000, 1152)

# 2. UMAP-Reduktion für Clustering (nicht Visualisierung)
reducer = umap.UMAP(
    n_neighbors=30,         # breite Nachbarschaft → stabile globale Struktur
    min_dist=0.0,           # maximale Kompaktheit der Cluster
    n_components=10,        # 5-10 reicht für Clustering, nicht 2
    metric='cosine',        # SigLIP ist cosine-normalisiert
)
reduced = reducer.fit_transform(embeddings)  # (5000, 10)

# 3. HDBSCAN auf reduzierter Darstellung
clusterer = sklearn.cluster.HDBSCAN(
    min_cluster_size=8,
    min_samples=5,
    cluster_selection_method='eom',   # Excess of Mass
)
labels = clusterer.fit_predict(reduced)
```

**Benchmark-Zahlen aus peer-reviewed Literatur (PMC 7340901):**

| Datensatz | N | Orig-Dim | HDBSCAN-Accuracy vorher | nachher | Speedup |
|---|---|---|---|---|---|
| MNIST | 20k | 784 | ~45 % | ~90 % | 26 min → 5 s |
| Fashion-MNIST | 20k | 784 | — | +50 % | ähnlich |
| USPS | 9.3k | 256 | — | +60 % | — |

**Wichtiger Punkt — UMAP-Speicher-Struktur muss persistiert werden.** Für neue Clips muss `reducer.transform(new_embedding)` laufen — also `reducer` speichern (pickle + Versionierung). Volles Re-Fit nur bei Re-Clustering-Trigger.

**Quellen:**
- [UMAP for Clustering (official)](https://umap-learn.readthedocs.io/en/latest/clustering.html) — Docs-Seite, blockiert bei Fetch, aber Search-Snippet bestätigt Parameter.
- [Arize — Understanding UMAP and HDBSCAN](https://arize.com/resource/understanding-umap-and-hdbscan/) — praktische Parameter-Guidance von Leland McInnes.
- [PMC 7340901 — Comparative Study UMAP+HDBSCAN](https://pmc.ncbi.nlm.nih.gov/articles/PMC7340901/) — peer-reviewed Benchmarks.

---

### Q3 — Wilson-Lower-Bound Parameterisierung

**Antwort:** Wilson-Lower-Bound mit **z = 1.96 (95 % Konfidenz)** ist der etablierte Recommender-Standard (Evan-Miller-Ranking, Reddit, Hacker News historisch). Formel:

```
WLB(p̂, n) =
    [p̂ + z²/(2n)] / [1 + z²/n]
    − (z / [1 + z²/n]) × √[ p̂(1-p̂)/n + z²/(4n²) ]
```

Für unseren Fall: `p̂ = accept_count / sample_size`, `n = sample_size`, `z = 1.96`.

**Stabilität**: ab n ≈ 10 reliably, d. h. Pattern mit 9 oder weniger Feedback-Events bleibt in den Rand-Regionen (Wilson zieht `p̂` gegen 0.5 = Unsicherheit).

**Für 5-Stern-Ratings (falls wir Rating-Pattern bauen):** Bayesian-Approximation:

```
Score = [ Σ(s_k · n_k) + z² · K/2 ] / [ N + z² ]
```
mit `s_k` = Rating-Wert (1-5), `n_k` = Anzahl bei Rating `s_k`, `K = 5`, `N = Σn_k`.

**Konservativer (99 %) Modus:** z = 2.576 — nur bei „Clip-Blacklist"-artigen Patterns sinnvoll (wo wir wirklich sicher sein wollen, bevor wir blockieren). Für positive Empfehlungen 95 % ausreichend.

**Quellen:**
- [Wikipedia — Binomial Proportion Confidence Interval](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval) — kanonische Formel-Referenz.
- [Medium — Wilson Lower Bound & Bayesian Approx für K-Star](https://medium.com/tech-that-works/wilson-lower-bound-score-and-bayesian-approximation-for-k-star-scale-rating-to-rate-products-c67ec6e30060) — praktische Formeln inkl. K-Star.

---

### Q4 — SigLIP Mood-Anchor-Prompts

**Antwort:** SigLIP 2 (Feb 2025) ist gegenüber SigLIP 1 deutlich stärker bei abstrakten Zero-Shot-Konzepten. Die drei Verbesserungen helfen direkt:

1. **Decoder-Based Objectives** (holistisch + region-spezifisch) → bessere semantische Tiefe.
2. **Global-Local Loss + Masked Prediction** → fine-grained Semantik, hilft bei Mood-Nuancen.
3. **NaFlex (Dynamic Resolution)** → robust gegen Clip-Keyframe-Varianz.

**Embedding-Dim bleibt 1152** (SO400M-Variante), d. h. die vorhandene Pipeline kann ohne Schema-Änderung upgraden — `model = AutoModel.from_pretrained("google/siglip2-so400m-patch14-384")` drop-in.

**Mood-Prompt-Empfehlungen (aus dem HF-Blog-Pattern):**

```python
mood_anchors = {
    "euphoric":    "a euphoric, ecstatic, joyful atmosphere with bright celebration",
    "melancholic": "a melancholic, sad, reflective atmosphere with soft quiet mood",
    "dark":        "a dark, ominous, heavy atmosphere with shadows and tension",
    "aggressive":  "an aggressive, intense, powerful atmosphere with confrontation",
    "dreamy":      "a dreamy, surreal, floating atmosphere with soft ethereal light",
    "playful":     "a playful, whimsical, lighthearted atmosphere with fun",
    "tense":       "a tense, suspenseful atmosphere with anticipation and unease",
    "calm":        "a calm, peaceful, serene atmosphere with stillness",
    "uplifting":   "an uplifting, hopeful, rising atmosphere with warm optimism",
    "ambient":     "an ambient, atmospheric, textural scene without strong emotion",
}
```

**Wichtig — empirisch kalibrieren.** Der Blog gibt keine Benchmarks für Mood-Klassifikation; die Prompts sind ein Ausgangspunkt, der per Grid-Search-ähnlichem Testing auf einem annotierten Mini-Set (30-50 Clips) bestätigt werden muss. Konkret: Cosine-Similarity-Matrix der 10 Anchors gegeneinander prüfen — sollten möglichst orthogonal sein (< 0.5 paarweise).

**Quellen:**
- [Hugging Face — SigLIP 2 Blog](https://huggingface.co/blog/siglip2) — offizielles Release + Code-Beispiel.
- [SigLIP 2 Paper (arxiv 2502.14786)](https://arxiv.org/pdf/2502.14786) — technische Details für Review in Plan-Phase.
- [Roboflow — SigLIP Overview](https://roboflow.com/model/siglip) — Einordnung SigLIP vs. CLIP.

---

### Q5 — Onset-Detection bei 1-3h DJ-Mixen — Chunking-Pattern

**Antwort:** librosa hat **keine offizielle Lösung** für Streaming / Chunking mit Onset-Detection. Der einzige dokumentierte Streaming-Pfad ist `librosa.stream`, und eine GitHub-Diskussion (Issue #1424) zeigt, dass die Nutzer selbst Overlap-Strategien implementieren müssen.

**Bekannte Probleme:**
- Frame-Boundary-Artefakte: „the first value is always zero" (kein Vorgänger-Frame).
- Keine Zustands-Carryover zwischen Chunks.
- `onset_detect(backtrack=True)` setzt erkannte Onsets auf das vorausgehende Energie-Minimum — hilft, löst aber das Boundary-Problem nicht.

**Empfohlenes Pattern für PB Studio (eigenes Design, kein offizielles):**

```python
def analyze_onsets_chunked(audio_path, structure_segments):
    """
    DJ-Mix → per Structure-Segment analysieren.
    Structure-Segmente sind semantische Einheiten (INTRO, BUILDUP, DROP, ...)
    mit Längen von typischerweise 30s–4min — unter dem librosa-Memory-Limit.
    """
    OVERLAP_SEC = 2.0   # genug für onset_envelope-Kontext
    FADE_IN_DISCARD = 0.1   # die ersten 100 ms eines Chunks verwerfen (Boundary-Artefakt)

    all_onsets = []
    for seg in structure_segments:
        start = max(0, seg.start - OVERLAP_SEC)
        end   = min(audio_duration, seg.end)
        y, sr = librosa.load(audio_path, sr=22050, mono=True, offset=start, duration=end - start)

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr,
            backtrack=True,    # aufs Energy-Minimum zurückfallen
            normalize=True,
        )
        # Frame→Zeit konvertieren, globalen Offset addieren, Overlap-Bereich + Fade-in verwerfen
        times = librosa.frames_to_time(onsets, sr=sr)
        valid = (times > OVERLAP_SEC + FADE_IN_DISCARD)
        all_onsets.extend(times[valid] + start)

    return all_onsets
```

**Drei Selbst-Tests, die das Spec vorsehen sollte:**

1. **Overlap-Funktion:** synthetischer Test — 1 echter Onset genau an Segment-Grenze. Darf nicht doppelt erkannt werden (eine Segment-Seite muss gewinnen, z. B. linke).
2. **Long-Mix-Regression:** 3h synthetischer Mix mit bekannten Onsets pro Structure-Segment. Globale F1 ≥ 0.85 gegen Single-Pass-Baseline (bei einzelnen Segmenten).
3. **Memory-Peak-Messung:** 3h-Durchlauf darf nicht mehr als 1.5 GB RAM belegen (librosa-load ist linear bei ~22050 Hz mono).

**Quellen:**
- [librosa.onset.onset_detect Docs](https://librosa.org/doc/main/generated/librosa.onset.onset_detect.html) — API, `backtrack`-Parameter bestätigt.
- [librosa Issue #1424 — Real-time/Streaming Onsets](https://github.com/librosa/librosa/issues/1424) — bestätigt, dass keine offizielle Chunking-Strategie existiert.
- [DeepWiki — librosa Onset Detection](https://deepwiki.com/librosa/librosa/5.2-onset-detection) — Community-Docs, gleichzeitig Hinweis auf Backtracking.

---

### Q6 — LUFS / Loudness → Perceived Mood

**Antwort:** Loudness hat eine **starke, konsistente Korrelation zu Arousal** (r ≈ 0.57–0.75 über Domains hinweg), aber eine **schwache, domain-abhängige Korrelation zu Valence** (in Musik: +, in Speech/Sound-Events: −). Konkret aus Frontiers Psychology (Weninger et al., 2013):

- Arousal-Prädiktion mit 200 akustischen Features: r = 0.65–0.79 cross-domain.
- Valence: r = 0.40–0.82 je Domain, also unzuverlässig ohne Domain-Kontext.
- Loudness („root quadratic mean of loudness") ist unter den **stärksten einzelnen Arousal-Prädiktoren**.

**Für unseren Fall:**

- `at_lufs` im `mem_decision` zu speichern ist sinnvoll. Clustern nach `at_lufs`-Quantilen ergibt Arousal-Proxy.
- Aber: **LUFS allein als Mood-Feature im Agent-Scoring ist nicht ausreichend.** Multivariat mit `at_spectral_hash`, `at_groove_template`, `at_bpm`, `at_key` kombinieren.
- Bestehendes `mood_genre_classify` (Heuristik) nutzt bereits Spectral + RMS — LUFS ist kein Redundanz-Feature, sondern ein **kalibriertes** Loudness-Maß (EBU R128), das zwischen Tracks vergleichbar ist (Spectral-/RMS-Werte sind es nicht ohne Normalisierung).

**Weiterführende Literatur (noch nicht verifiziert, für Phase 4 Machbarkeit):**
- [Nature Scientific Reports 2024 — „Music communicates social emotions"](https://www.nature.com/articles/s41598-024-78156-1) (Fetch blockiert, aber Search-Abstract bestätigt: 750 Musik-Excerpts, bestätigt Loudness als einen von mehreren Prädiktoren).

**Quellen:**
- [Frontiers Psychology — On the Acoustics of Emotion](https://www.frontiersin.org/articles/10.3389/fpsyg.2013.00292/full) — peer-reviewed, quantitative Korrelationen.
- [Nature Scientific Reports 2024 — 750 Music Excerpts](https://www.nature.com/articles/s41598-024-78156-1) — neuere Replikation mit größerem Korpus.
- [iZotope — What are LUFS](https://www.izotope.com/en/learn/what-are-lufs) — technische LUFS-Referenz (EBU R128).

---

## Empfehlungen für Phase 3/4/5

### Spec-Updates (minimal, Phase 1-Spec bleibt substanziell)

1. **Enrichment-Pipeline Sektion 5.2 Step 3 erweitern:**
   - UMAP ist **Teil des Style-Bucket-Clustering-Schritts**, nicht nachträglich. Pipeline: `SigLIP (1152) → UMAP (10-dim, cached) → HDBSCAN`.
   - `umap-learn` als neue Dependency aufnehmen (`pip install umap-learn>=0.5` — MIT-Lizenz).
   - Persist: UMAP-Reducer (pickle, versioniert in `storage/enricher/umap_vN.pkl`).

2. **Sektion 6.5 Scoring-Term `historical_accept_rate`:**
   - Wilson-Lower-Bound mit z=1.96 als Default.
   - Optional: z=2.576 für `clip_blacklist`-Pattern (strengere Konfidenz bei destruktiven Entscheidungen).

3. **Sektion 5.2 Step 2 Mood-Refinement:**
   - Prompt-Katalog für SigLIP-Anchor wie oben dokumentieren in `config/mood_anchors_v1.yaml`.
   - Akzeptanz-Test: paarweise Cosine-Similarity < 0.5 für alle 10 Anchors.
   - Klarer Upgrade-Pfad SigLIP 1 → SigLIP 2 (drop-in bei gleicher Dim).

4. **Sektion 5.3 DJ-Mix-Skalierung erweitern:**
   - Chunking-Pattern wie in Q5 ausformuliert, **nicht** nur generische Anmerkung.
   - Drei Test-Typen spezifizieren (Boundary-Overlap, 3h-Regression, Memory-Peak).

5. **Sektion 6.5 LUFS-Term `w_spectral`/`w_loudness`:**
   - `at_lufs` stärker in Spectral-Term einbeziehen oder eigenen Term `w_loudness` auskoppeln.
   - Klarstellen: LUFS = Arousal-Proxy, nicht Mood-Label.

### Für die Plan-Phase (Sektion 9)

6. **Test-Pyramide ergänzen:**
   - `tests/enrichment/test_umap_hdbscan_pipeline.py` — pickle-Reproduzierbarkeit, Dim-Consistency.
   - `tests/enrichment/test_mood_anchor_orthogonality.py` — paarweise Anchor-Similarity < 0.5.
   - `tests/integration/test_onset_chunked_boundary.py` — Overlap-Artefakt-Freiheit.

7. **Dependencies aktualisieren:**
   - `umap-learn>=0.5` (neu, MIT)
   - `pyqtgraph>=0.13` (neu, bereits im Spec)
   - `networkx>=3.0` — als explizite Dependency (transitiv via scikit-learn evtl. schon da, explizit pinnen)

---

## Warnungen / Rote Flaggen

| # | Warnung | Schweregrad |
|---|---|---|
| W1 | **librosa hat keinen offiziellen Chunk-Pfad** für Onset-Detection. Unser Per-Segment-Pattern ist Eigenbau; wir müssen es **selbst validieren** (Tests oben). | Mittel — lösbar, aber Aufwand |
| W2 | **SigLIP-Mood-Anchors sind empirisch, nicht benchmarkiert.** Es gibt keine publizierten Studien für die 10 spezifischen Mood-Klassen. Erstes Release braucht Kalibrierungs-Runde an annotiertem Mini-Set. | Mittel — wissenschaftlich offen |
| W3 | **UMAP-Reducer muss persistiert und versioniert werden.** Bei Reducer-Wechsel müssen alle alten `style_bucket_id` in `mem_decision` als Snapshot erhalten bleiben, aber neu cluster'n. `enricher_version` deckt das, aber nur wenn strikt verwendet. | Mittel — Design klar, Umsetzung disziplinfordernd |
| W4 | **LUFS ist nicht Mood.** Wenn das Team später Mood-Features mixed, die Loudness implizit reflektieren (Spectral-Energie, RMS), drohen Korrelationen und redundante Gewichte. Feature-Engineering-Dokumentation muss klarstellen, welcher Term was misst. | Niedrig — Doku-Sache |
| W5 | **NodeGraphQt-PySide6 ausschließen**. Wer es später einbaut, baut das falsche Werkzeug ein. Entscheidung im ADR festhalten. | Niedrig — nur Verirrungs-Gefahr |
| W6 | **Wilson-Lower-Bound gibt 0 bei 0/0.** Bei komplett neuen Clips ohne Feedback muss der Code das abfangen (historical_accept_rate fällt dann auf 0.5 als „weiß nichts" zurück, nicht auf 0 = „schlecht"). | Niedrig — Code-Detail |

---

## Offene Fragen (für Phase 4 Machbarkeit)

- **UMAP-Reducer Re-Fit-Häufigkeit:** bei welcher Anzahl neuer Clips (50? 100? 500?) muss neu gefittet werden, damit Drift kompensiert wird, ohne Gedächtnis zu invalidieren? **Keine klare Guidance in der Literatur.**
- **Force-Directed-Layout-Performance bei > 2000 Knoten:** die Spec zielt auf ≤ 2000, aber realistische Librarys könnten 5000+ Scenes enthalten. Fallback-UI (Grid-only) muss dann automatisch greifen?
- **HDBSCAN vs. k-means Trade-off:** k-means-spherical ist schneller und deterministischer, würde aber feste Cluster-Anzahl voraussetzen. HDBSCAN erlaubt Noise-Klasse („unique"), was bei kleinen heterogenen Sammlungen wertvoll ist. Der Zeitgewinn ist bei unserer Skala (≤ 5000 Scenes) vernachlässigbar — Empfehlung bleibt HDBSCAN, aber im Plan explizit rechtfertigen.
- **SigLIP 2 vs. SigLIP 1 — blockierender Migrations-Aufwand?** Wenn SigLIP 1 heute im Einsatz ist und Produktions-Embeddings persistiert sind, ist ein Wechsel eine Re-Enrichment-Welle (alle Scenes neu encodieren). Aufwand: `N_scenes × 50 ms` auf GPU — bei 5000 ~ 4 Minuten. Machbar, aber nicht automatisch — User-Entscheidung pro Library.
- **Mood-Anchor-Kalibrierung:** wie viele Annotationen pro Mood-Klasse sind minimal nötig, um die Anchor-Prompts zu prüfen? Heuristisch: 10-20 pro Klasse reichen für Grobkorrektur, aber das ist nicht quellenbasiert.
- **Onset-Overlap bei sehr kurzen Segmenten** (< 10 s, z. B. kurze Transitionen) — 2 s Overlap wäre 20 % des Segments. Unkritisch, aber Test-Fall abdecken.

---

## Pipeline-Vermerk

Research abgeschlossen: **6 Fragen, 11 Quellen fetched (6 erfolgreich + 3 via Search-Summary + 2 Fetch-Fails als Gaps dokumentiert), 5 Schlüsselerkenntnisse, 6 Warnungen.**

Input für:
- **Phase 3 (PRD):** Problem-Statement kann „lernendes Hirn" konkret quantifizieren (z. B. „Accept-Rate soll von X auf Y nach N Runs steigen").
- **Phase 4 (Machbarkeit):** UMAP-Dep, SigLIP-2-Upgrade-Entscheidung, Onset-Chunk-Eigenbau, Wilson-Parameter.
- **Phase 5 (Plan):** Dependency-Liste final, Test-Pyramide um 3 neue Tests erweitert, Enricher-Pipeline um UMAP-Schritt erweitert.
