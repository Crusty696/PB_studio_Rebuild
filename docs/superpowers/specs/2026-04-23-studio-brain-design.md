# Studio Brain — Design-Dokument

**Datum:** 2026-04-23
**Projekt:** PB Studio Rebuild
**Phase:** Idea-Pipeline — Phase 1 (Brainstorming/Design)
**Status:** In Review
**Related:** nachgelagert Phase 2 (Recherche), Phase 3 (PRD), Phase 4 (Machbarkeit), Phase 5 (Plan)

---

## 1. Problem & Ziele

### 1.1 Problem

Der bestehende Pacing-Agent in PB Studio ist blind für drei Dinge:

- **Stilistische Kollisionen** zwischen aufeinanderfolgenden Clips (Nature-Shot → Urban-Grit ohne Logik).
- **Rollen-Blindheit**: Hero, Transition, Detail, Filler, Establishing werden nicht unterschieden — alle Clips gelten als gleichwertig.
- **Mood-/Vibe-Blindheit**: Clip-Mood (melancholisch, kraftvoll, verspielt …) fließt nicht in die Selektion; nur Motion + Energy entscheiden.

Der Agent sieht Clips nur als *Motion + Embedding*, nicht als „Dinge mit Charakter & Rolle". Er lernt außerdem nicht aus seinen Entscheidungen.

### 1.2 Ziele

1. **Qualität der Cuts verbessern** durch reichere Entscheidungs-Kriterien.
2. **Fehler vermeiden** (wiederholte Clips, Stil-Kollisionen, Rollen-Mismatch).
3. **Erinnerungen aufbauen** — jeder Pacing-Run und jedes User-Feedback wird persistiert; der Agent wird über Zeit besser.

### 1.3 Nicht-Ziele

- Externe Obsidian-Integration. Das Studio-Brain ist **nicht** Teil des Brain-Bug-Vaults (der ist für Entwicklung).
- App-Wechsel (der User bleibt durchgehend in PB Studio).
- Manuelles Labeln von Clips durch den User (Source-of-Truth ist die Auto-Pipeline).

---

## 2. Ansatz-Wahl

Drei Ansätze wurden evaluiert (siehe Brainstorming-Protokoll):

| | Ansatz | Ziele-Deckung |
|---|---|---|
| A | Struktur-Hirn (statisch) | Qualität ✓ · Fehler ~ · Erinnerungen ✗ |
| M | Gedächtnis-Hirn (lernt) | Qualität ~ · Fehler ✓✓ · Erinnerungen ✓✓ |
| **H** | **Struktur + Gedächtnis (gewählt)** | **Qualität ✓✓ · Fehler ✓✓ · Erinnerungen ✓✓** |

**Entscheidung: H.** Nur H deckt alle drei Ziele zu 100% ab. Kein Cold-Start durch die Struktur-Schicht, kontinuierliches Lernen durch die Gedächtnis-Schicht.

---

## 3. Architektur

### 3.1 Schichten & Fenster

```
┌─────────────────────────────────────────────────────────────┐
│  PB Studio (PySide6)                                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MainWindow (bestehend)                              │   │
│  │   ├─ Timeline, MediaGrid, Pacing-Controls …          │   │
│  │   └─ [Studio-Brain öffnen] Button + Shortcut         │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼   (separates QMainWindow)       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  StudioBrainWindow (on-demand, non-modal, Singleton) │   │
│  │  Tabs: [Struktur] [Gedächtnis] [Audit] [Steer]       │   │
│  │  + Story-Map (QDialog on-demand pro Song)            │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                 │
│  ┌──────────────────┬─────┴──────┬─────────────────────┐    │
│  │ STRUKTUR-LAYER   │ GEDÄCHTNIS │ AGENT-LAYER         │    │
│  │ (statisch, auto) │ (lernt)    │ (nutzt beides)      │    │
│  │ • Rolle          │ • Runs     │ • Hard-Rules        │    │
│  │ • Mood refined   │ • Decisions│ • Variations-Budget │    │
│  │ • Style-Bucket   │ • Feedback │ • Kollisions-Check  │    │
│  │ • Compat-Graph   │ • Patterns │ • Soft-Scoring      │    │
│  └──────────────────┴────────────┴─────────────────────┘    │
│                           │                                 │
│                           ▼                                 │
│                    SQLite (eine DB, zwei Tabellen-Familien) │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Kernprinzipien

1. **Ein Fenster, vier Perspektiven.** Studio-Brain ist eigenes `QMainWindow`, nicht modal, kann parallel zum Main-Window offen bleiben.
2. **Strikte Schichtentrennung.** Struktur-Layer kennt kein Gedächtnis. Gedächtnis-Layer kennt keine Agent-Logik. Nur der Agent-Layer liest beide.
3. **Agent schreibt ins Gedächtnis, nie in die Struktur.** Struktur ist read-only für den Agent; Gedächtnis ist append-only durch Agent und User-Feedback.
4. **Feedback ist integriert, nicht Extra-Schritt.** Accept/Reject/Skip passiert in der Timeline-UI (Shortcut-basiert), nicht in einem separaten Dialog.
5. **Eine SQLite-DB, klar getrennte Tabellen-Familien.** Prefix `struct_*` vs `mem_*`.

### 3.3 Die Analyse-Pipeline als Nährboden

Der Studio-Brain **dupliziert keine Analyse** — er konsumiert die Ergebnisse aller bestehenden Schritte und verdichtet sie:

**Video-Analyse (8 Steps):** `metadata_extract`, `scene_detection`, `motion_scores` (RAFT), `keyframe_extraction`, `siglip_embeddings`, `vector_db_storage`, `ai_scene_caption` (Gemma), `scene_db_storage`.

**Audio-Analyse (9 Steps):** `bpm_detection` + `beat_grid` (beat_this, chunked 10-min für VRAM-Schutz), `waveform_analysis` (3-Band Rekordbox), `key_detection` (Key + Confidence + Modulation + Harmonic-Tension-Kurve), `lufs_analysis`, `mood_genre_classify` (mood + genre + sub_genre), `spectral_analysis` (8 Mel-Bänder), `structure_detection` (INTRO/BUILDUP/DROP/BREAKDOWN/…, inkl. `is_dj_mix`-Flag), `stem_separation` (DEMUCS), `onset_detection` (kick/snare/hihat + groove_template + syncopation_score).

**Alle diese Outputs fließen in den Decision-Context-Snapshot** jeder Pacing-Entscheidung (Sektion 5).

---

## 4. Datenmodell

### 4.1 Struktur-Layer

```sql
CREATE TABLE struct_clip_tags (
  scene_id           INTEGER PRIMARY KEY,
  role               TEXT    NOT NULL,        -- hero|action|transition|detail|establishing|filler|unknown
  role_confidence    REAL    NOT NULL,
  mood_refined       TEXT    NOT NULL,        -- euphoric|melancholic|dark|aggressive|dreamy|playful|tense|calm|uplifting|ambient
  mood_confidence    REAL    NOT NULL,
  style_bucket_id    INTEGER NOT NULL,
  style_distance     REAL    NOT NULL,
  enriched_at        TIMESTAMP NOT NULL,
  enricher_version   TEXT    NOT NULL,
  FOREIGN KEY (scene_id)        REFERENCES scene(id) ON DELETE CASCADE,
  FOREIGN KEY (style_bucket_id) REFERENCES struct_style_bucket(id)
);
CREATE INDEX idx_struct_clip_tags_role  ON struct_clip_tags(role);
CREATE INDEX idx_struct_clip_tags_mood  ON struct_clip_tags(mood_refined);
CREATE INDEX idx_struct_clip_tags_style ON struct_clip_tags(style_bucket_id);

CREATE TABLE struct_style_bucket (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  name               TEXT    NOT NULL UNIQUE,
  description        TEXT,
  centroid_embedding BLOB    NOT NULL,        -- np.float32 × 1152
  member_count       INTEGER NOT NULL,
  created_at         TIMESTAMP NOT NULL,
  enricher_version   TEXT    NOT NULL
);

CREATE TABLE struct_compat_edge (
  scene_id_a         INTEGER NOT NULL,
  scene_id_b         INTEGER NOT NULL,
  cosine_similarity  REAL    NOT NULL,
  rank_in_a          INTEGER NOT NULL,        -- 1..20
  PRIMARY KEY (scene_id_a, scene_id_b),
  FOREIGN KEY (scene_id_a) REFERENCES scene(id) ON DELETE CASCADE,
  FOREIGN KEY (scene_id_b) REFERENCES scene(id) ON DELETE CASCADE
);
CREATE INDEX idx_struct_compat_edge_a_rank ON struct_compat_edge(scene_id_a, rank_in_a);
```

### 4.2 Gedächtnis-Layer

```sql
CREATE TABLE mem_pacing_run (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  audio_track_id     INTEGER NOT NULL,
  started_at         TIMESTAMP NOT NULL,
  completed_at       TIMESTAMP,
  is_dj_mix          BOOLEAN NOT NULL,
  total_duration_sec REAL    NOT NULL,
  total_cuts         INTEGER NOT NULL DEFAULT 0,
  agent_version      TEXT    NOT NULL,
  weights_profile    TEXT    NOT NULL,
  user_rating        INTEGER,
  user_notes         TEXT,
  steer_snapshot     JSON,                    -- archivierter Steer-State
  FOREIGN KEY (audio_track_id) REFERENCES audio_track(id)
);

CREATE TABLE mem_decision (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id             INTEGER NOT NULL,
  sequence_idx       INTEGER NOT NULL,

  -- WANN im Mix
  at_timestamp_sec   REAL    NOT NULL,
  at_beat_idx        INTEGER,
  at_structure_segment_id INTEGER,

  -- AUDIO-Kontext (Snapshot)
  at_bpm             REAL,
  at_energy          REAL,
  at_section_type    TEXT,
  at_key             TEXT,
  at_key_confidence  REAL,
  at_key_modulation  BOOLEAN,
  at_harmonic_tension REAL,
  at_mood_audio      TEXT,
  at_genre           TEXT,
  at_sub_genre       TEXT,
  at_spectral_hash   TEXT,
  at_groove_template TEXT,
  at_lufs            REAL,

  -- VIDEO-Kontext (Snapshot)
  scene_id           INTEGER NOT NULL,
  clip_role          TEXT    NOT NULL,
  clip_mood_refined  TEXT    NOT NULL,
  clip_style_bucket_id INTEGER NOT NULL,
  clip_motion_score  REAL,

  -- ENTSCHEIDUNG
  agent_score        REAL    NOT NULL,
  agent_rationale    JSON    NOT NULL,        -- term_contributions, alternatives, budget_state, fallback-Flags

  -- FEEDBACK
  user_verdict       TEXT,                    -- accept|reject|skip|modify|null
  user_verdict_at    TIMESTAMP,
  user_rating        INTEGER,

  FOREIGN KEY (run_id)   REFERENCES mem_pacing_run(id) ON DELETE CASCADE,
  FOREIGN KEY (scene_id) REFERENCES scene(id)
);
CREATE INDEX idx_mem_decision_run          ON mem_decision(run_id, sequence_idx);
CREATE INDEX idx_mem_decision_scene        ON mem_decision(scene_id);
CREATE INDEX idx_mem_decision_verdict      ON mem_decision(user_verdict);
CREATE INDEX idx_mem_decision_context_hash ON mem_decision(at_genre, at_section_type, at_bpm);

CREATE TABLE mem_learned_pattern (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern_type       TEXT    NOT NULL,        -- context_preference | clip_blacklist | clip_whitelist | style_affinity
  context_fingerprint JSON,
  target_ref         JSON,
  stat_accept_count  INTEGER NOT NULL DEFAULT 0,
  stat_reject_count  INTEGER NOT NULL DEFAULT 0,
  stat_sample_size   INTEGER NOT NULL DEFAULT 0,
  confidence         REAL    NOT NULL,        -- Wilson-Lower-Bound
  last_updated       TIMESTAMP NOT NULL
);
CREATE INDEX idx_mem_learned_pattern_type ON mem_learned_pattern(pattern_type);

CREATE TABLE mem_user_feedback_event (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  decision_id        INTEGER,
  run_id             INTEGER NOT NULL,
  event_type         TEXT    NOT NULL,        -- accept|reject|skip|rate|replace
  payload            JSON,
  created_at         TIMESTAMP NOT NULL,
  FOREIGN KEY (run_id) REFERENCES mem_pacing_run(id) ON DELETE CASCADE
);
```

### 4.3 Design-Entscheidungen

- **`mem_decision` denormalisiert per Design.** Audio-Kontext wird per Snapshot gespeichert, nicht per FK zu Beatgrid/Structure. Grund: Re-Analysen ändern historische Werte sonst rückwirkend. Snapshot = immutable truth.
- **`mem_learned_pattern` getrennt von `mem_decision`.** Rohdaten vs. aggregierte Erkenntnisse. Patterns werden periodisch aus Decisions re-berechnet.
- **`confidence` = Wilson-Lower-Bound**, nicht naives `accept/total`. Frische Patterns mit wenig Daten dominieren nicht.
- **`user_verdict` nullable.** User muss nicht jeden Cut bewerten.
- **`ON DELETE CASCADE` nur gegen Parent-Run/Scene**, nicht transitive Patterns — gelöschte Clips löschen historische Spur nicht aus.

---

## 5. Enrichment-Pipeline

### 5.1 Neuer Worker

`workers/structure_enrichment.py` — ausgelöst nach `AnalysisStatus.scene_db_storage=done` oder manuell via „Re-Enrich"-Button. Neuer Step in `AnalysisStatus.VIDEO_STEPS`: `structure_enrichment`.

**GPU-frei:** Alle vier Enrichment-Steps laufen auf CPU, konsumieren nur persistierte Pipeline-Outputs. Bewusste Designentscheidung, um GPU nicht weiter zu belasten (SigLIP/RAFT/Gemma/DEMUCS sind bereits konkurrierend).

### 5.2 Die vier Steps

**Step 1 — `classify_role(scene) -> (role, confidence)`**

Regelbasiert. Hierarchische if/elif-Kette auf `motion_score`, `duration`, `ai_caption.tags`. Konfigurierbar via `config/enrichment_rules.yaml`. Deterministisch, erklärbar, 0 Trainingsdaten nötig.

Output-Klassen: `hero | action | transition | detail | establishing | filler | unknown`.

**Step 2 — `refine_mood(scene) -> (mood, confidence)`**

Cosine-Similarity des SigLIP-Embeddings gegen 10 vorberechnete Mood-Anchor-Embeddings (persistiert in `config/mood_anchors.npz`). Bestehende `ai_mood` (4-Klassen-Output von Gemma) dient als Prior (Gewicht 0.6, konfigurierbar).

Output-Klassen: `euphoric | melancholic | dark | aggressive | dreamy | playful | tense | calm | uplifting | ambient`.

**Step 3 — `assign_style_bucket(scene)`**

- Initial-Clustering: `sklearn.cluster.HDBSCAN` (in sklearn 1.3+, schon installiert) mit `min_cluster_size=8, min_samples=4` auf allen 1152-dim SigLIP-Embeddings.
- Inkrementell (neuer Clip): Nearest-Centroid-Zuweisung, kein Re-Clustering pro neuem Clip.
- Re-Clustering manuell per Button oder automatisch bei ≥ 50 neuen Clips (Config-Schwelle).
- Bucket-Namen: häufigste `ai_caption.tags` der Mitglieder (Top-3) + optional LLM-Prägnanz.

**Step 4 — `rebuild_compat_edges_for_clip(clip_id)`**

Top-20 Cosine-Nachbarn pro Scene aus dem In-Memory-Embedding-Cache (via `vector_db_service`). Gespeichert in beide Richtungen (`scene_id_a`/`scene_id_b` als separate Rows mit eigener `rank_in_a`).

### 5.3 DJ-Mix-Skalierung

Enrichment ist scene-basiert, unabhängig von Audio-Dauer. **Aber:** Bestehender `onset_rhythm_service.MAX_DURATION_SEC = 1800` (30 min, M-17-Fix gegen RAM-Exhaustion) greift bei 1–3h DJ-Mixen. Fix:

```python
# services/onset_rhythm_service.py
def analyze(audio_path, structure_segments=None):
    if structure_segments and len(structure_segments) > 0:
        return _analyze_per_segment(audio_path, structure_segments)
    return _analyze_whole(audio_path)
```

Output-Schema bleibt identisch. Kein Breaking-Change.

### 5.4 Versionierung

`enricher_version` in `struct_clip_tags` und `struct_style_bucket`. Re-Runs nach Regel-Updates überschreiben nur alte Zeilen.

---

## 6. Pacing-Agent-Integration

### 6.1 Vierstufige Entscheidungs-Pipeline

```
Kandidaten = alle Scenes der Library

  Stufe 1: HARD RULES                   (disqualifizierend)
    section × role Matrix
    optional: Key × Clip-Mood-Gate bei hoher Tension

  Stufe 2: VARIATIONS-BUDGET            (disqualifizierend)
    Sliding-Window-Zähler pro (scene_id | style_bucket | mood | role)

  Stufe 3: KOLLISIONS-CHECK             (Penalty-Weiterreichung)
    Compat-Edge zum Vorgänger; kein-Edge → Penalty

  Stufe 4: SOFT-SCORING                 (Ranking)
    gewichtete Summe von 10+ Termen (Struktur + Gedächtnis + Audio)
    Top-1 wird gewählt (Top-K bei „Varianz-Modus")

  → Persist: mem_decision mit vollem Context-Snapshot
```

### 6.2 Stufe 1 — Hard Rules

Default `config/pacing_rules.yaml`:

```yaml
section_role_matrix:
  intro:      [establishing, ambient, detail]
  warmup:     [establishing, hero_low_motion, detail]
  buildup:    [hero, action, transition]
  drop:       [hero, action]
  breakdown:  [detail, ambient, establishing]
  outro:      [establishing, detail, ambient]
  verse:      [hero, detail]
  chorus:     [hero, action]
  bridge:     [transition, detail]
  transition: [transition, action, hero]

key_mood_gate:
  enabled: false
  condition: "at_harmonic_tension > 0.7"
  forbidden_moods: [calm, ambient, dreamy]
```

**Konsequenz bei leerer Kandidatenmenge:** Regel wird aufgeweicht (nächste Tier), `fallback=true` im Rationale, Warnung im Audit-Tab. Niemals leerer Cut.

### 6.3 Stufe 2 — Variations-Budget

```yaml
budgets:
  scene_id:     { max_per_window: 1, window_sec: 45 }
  style_bucket: { max_per_window: 3, window_sec: 30 }
  mood_refined: { max_per_window: 4, window_sec: 30 }
  role:         { max_per_window: 5, window_sec: 30 }
```

**DJ-Mix-Edgefall:** Bei `is_dj_mix=true` werden alle Budgets an jeder Structure-Segment-Grenze zurückgesetzt. Zusätzlich globaler `scene_id` `max=5 per whole_mix`.

### 6.4 Stufe 3 — Kollisions-Check

- Lookup `struct_compat_edge(P, C)`.
- Keine Edge **oder** `cosine_similarity < 0.55` (konfig) → **Penalty** an Stufe 4.
- Hard-Reject nur in Profil `collision_strict=true` (nicht Default; verhindert leere Kandidaten bei kleiner Library).

### 6.5 Stufe 4 — Soft-Scoring (alle Terme)

```python
score(clip, context) = (
    w_role        * role_fit(section, clip.role)
  + w_style       * style_compat(predecessor, clip)
  + w_mood_video  * mood_match(audio.mood, clip.mood_refined)
  + w_mood_audio  * mood_match(audio.mood_audio, clip.mood_refined)
  + w_genre       * genre_prior(audio.genre, clip.style_bucket)
  + w_key         * key_prior(audio.key, clip.mood_refined)
  + w_tension     * tension_fit(audio.harmonic_tension, clip.role)
  + w_energy      * energy_match(audio.energy, clip.motion_score)
  + w_spectral    * spectral_fit(audio.spectral_hash, clip)
  + w_groove      * groove_fit(audio.groove_template, clip.motion_score)
  + w_memory      * historical_accept_rate(context_fingerprint, clip)
  - w_collision   * collision_penalty(predecessor, clip)
  - w_freshness   * staleness_penalty(clip, window)
)
```

**Default-Gewichte (`config/pacing_weights/default.yaml`):**

```yaml
w_role:       0.25
w_style:      0.15
w_mood_video: 0.10
w_mood_audio: 0.10
w_genre:      0.15
w_key:        0.10
w_tension:    0.08
w_energy:     0.15
w_spectral:   0.05
w_groove:     0.07
w_memory:     0.20        # Confidence-gated; Wilson-Lower-Bound im Pattern regelt den realen Einfluss
w_collision:  0.10        # Penalty
w_freshness:  0.05        # Penalty
```

**Wichtig:** Alle Terme sind **von Tag 1 verdrahtet**. Memory-abhängige Terme (`w_memory`, `w_genre`, `w_key`, `w_spectral`) sind durch die Wilson-Confidence im Pattern gedämpft, nicht durch künstlich kleine Gewichte. Das garantiert ein **konsistentes Gedächtnis vom ersten Run an** (alle Context-Felder werden erfasst), während schwache Patterns noch keinen Einfluss haben.

### 6.6 Genre-spezifische Weights-Profile

DJ-Mix kann per Structure-Segment das Genre seiner Teilspur bestimmen und das Weights-Profil mid-run wechseln:

```
config/pacing_weights/
  ├── default.yaml
  ├── psytrance.yaml
  ├── house.yaml
  └── dj_mix_auto.yaml    # bei is_dj_mix=true default
```

`mem_pacing_run.weights_profile` speichert, welches Profil (ggf. welche Folge) aktiv war.

### 6.7 Memory-Feedback-Loop

- Jedes `mem_user_feedback_event` aktualisiert `mem_decision.user_verdict`.
- Asynchron (`workers/memory_updater.py`) re-aggregiert betroffene `mem_learned_pattern`-Zeilen. Trigger: nach Run-Ende oder nach N=20 neuen Events.
- Live-Update im Pacing-Agent wird **nicht** gemacht (Performance).

### 6.8 Performance-Budget Agent

- Zielkosten pro Cut-Entscheidung: **≤ 20 ms** bei 500 Kandidaten (vektorisierte NumPy-Matrix-Berechnung).
- Memory-Pattern-Lookup: LRU-gecacht pro Run (maxsize=256).
- 60-min-Track × 0.5 Cuts/s = 1800 Cuts × 20 ms = ~36 s reine Scoring-Zeit.

---

## 7. Studio-Brain-Fenster (UI)

### 7.1 Technische Basis

**Datei:** `ui/studio_brain_window.py` → `StudioBrainWindow(QMainWindow)`.
**Lifecycle:** Non-modal Singleton; Schließen versteckt (State bleibt). Eigene QSettings-Section.
**Datenzugriff:** via neuem `services/brain_service.py` — cached aggregierte Views, invalidiert bei Enrichment-/Run-Events.

**Widget-Stack:**

| Komponente | Widget |
|---|---|
| Graph-View | `QGraphicsScene` + `QGraphicsView` mit Custom-Items (Force-Directed-Layout offline berechnet) |
| Clip-Grid | `QListView` mit Custom-Delegate (Pattern aus `media_grid.py`) |
| Tabellen | `QTableView` + `QAbstractTableModel` |
| Inspector | `QScrollArea` + `QFormLayout` |
| Plots (Tension, Segment-Strip, Story-Map) | **`pyqtgraph>=0.13`** (neu zu requirements.txt hinzufügen) |

### 7.2 Tab 1 — „Struktur"

**Zweck:** Library-Überblick. Was hab ich? Wie hängt's zusammen?

**Layout:** Links Filter + Stats; Mitte Graph oder Grid (umschaltbar); Rechts Inspector.

**Filter:** Role / Mood / Style / min-Confidence / Usage (unused | 1+ | 5+).

**Graph-Mode:** Force-Directed, Knoten = Scene, Farbe = Style-Bucket, Größe = Usage-Count, Kanten aus `struct_compat_edge`. Klick → Inspector. Shift-Klick → Sub-Graph.

**Grid-Mode:** Thumbnails sortiert nach Style-Bucket (gleiche Farbe = gleicher Cluster).

**Stats-Panel:** Clip-/Scene-Anzahl, Anzahl Style-Buckets, Noise-Count, Mood-Coverage (zeigt Lücken: „keine playful-Clips!").

**Inspector (rechts, wenn Clip selektiert):** Thumbnail + role (mit Confidence) + mood_refined + style_bucket + motion_score + ai_caption + Top-5-Nachbarn (klickbar) + **Historische Usage aus Gedächtnis** (x Accepts / y Rejects / % Accept-Rate).

**Selection-Actions:** „Boost in next run" / „Exclude in next run" (feeds Tab 4 Steer).

### 7.3 Tab 2 — „Gedächtnis"

**Zweck:** Was hat der Agent aus der Vergangenheit gelernt?

**Layout:** Links Run-Timeline (chronologisch, mit Run-Rating + Cut-Count); Rechts gelernte Pattern-Tabelle (mit Confidence).

**Pattern-Typen:** `context_preference`, `clip_blacklist`, `clip_whitelist`, `style_affinity`.

**Drill-Down:** Klick auf Pattern-Zeile → zeigt die zugrundeliegenden `mem_decision`-Einträge.

**Destruktive Aktion:** „Reset gelernte Muster" → Confirm-Dialog + automatisches Backup.

### 7.4 Tab 3 — „Audit" (Post-Run Deep-Dive)

**Zweck:** Warum hat der Agent bei diesem Run das gemacht, was er gemacht hat?

**Layout:**
- Oben: Run-Selector + Rating-Control + [Story-Map öffnen]-Button.
- Bei `is_dj_mix=true`: horizontaler **Segment-Strip** (Click springt zum Segment).
- Mitte-Links: Cut-Tabelle (Index / Timestamp / Section / Clip / Role / User-Verdict).
- Mitte-Rechts: **Term-Contributions-Panel** (pro gewähltem Cut: aufgeschlüsselter Score, Alternativen mit Rang 2-3, Budget-State zum Zeitpunkt, Flags wie `fallback`/`forced`).

**Filter:** „nur rejected" / „nur fallback" / „nur hohe Tension".

### 7.5 Tab 4 — „Steer" (Pre-Run-Lenkung)

**Zweck:** Nächsten Run bewusst beeinflussen, ohne Gedächtnis zu verfälschen.

**Controls:**
- **Audio-Track-Auswahl** + **Weights-Profile-Dropdown** + „Profil bearbeiten" (öffnet YAML in externem Editor).
- **Pins:** Clip → Section-Binding (hart: muss / weich: Prio).
- **Excludes:** Clip oder Style-Bucket aus diesem Run raus (mit optionaler Begründung).
- **Boosts:** Style-Bucket / Mood / Role → `+X%`-Gewichtung, optional Section-scoped.
- **Vorschau:** zeigt verwendbare-Clip-Count und Structure-Coverage-Warnung.
- **[▶ Run starten mit diesen Einstellungen]**-Button.

**Persistenz:** In kleiner `steer_overrides`-Tabelle (run-scoped), nach Run in `mem_pacing_run.steer_snapshot` (JSON) archiviert. Kein Gedächtnis-Einfluss.

### 7.6 Story-Map (on-demand)

**Trigger:** Button im Audit-Tab oder Timeline-Kontextmenü.
**Widget:** eigenes `QDialog` (nicht modal).
**Inhalt:**
- Audio-Zeile (Waveform + Section-Strip)
- Clip-Strip (Thumbnails in Cut-Reihenfolge mit Role-Labels)
- Tension-Kurve (aus `harmonic_tension_curve`)
- Mood-Verlauf (farbcodiert)

Zoomable, exportierbar als PNG/SVG. Klick auf Clip-Thumb springt in MainWindow-Timeline.

### 7.7 Feedback-UI (NICHT im Studio-Brain)

Damit Feedback im Review-Flow passiert, wird es in der **Timeline** verortet:

- **Kontextmenü** auf Cut: `[✓ Akzeptieren (A)] [✗ Verwerfen (R)] [⟲ Ersetzen (E)] [⭐ Bewerten 1-5]`.
- **Shortcuts** im Timeline-Focus: `A`/`R`/`S`/`1-5`; `Shift+1-5` für ganzen Run.
- **Visuelle Indikatoren** auf Timeline-Clip: grün/rot/gelb Punkt; Tooltip zeigt Agent-Rationale kurz.
- **Write-Path:** Events gehen in separatem Thread in `mem_user_feedback_event` + update `mem_decision.user_verdict`. Pattern-Re-Aggregation async.

---

## 8. Performance, VRAM-Budget, Error-Handling

### 8.1 Performance-Profil

| Operation | Device | 1000 Scenes | 5000 Scenes |
|---|---|---|---|
| Enrichment total (ohne Re-Clustering) | CPU | ~12 s | ~80 s |
| HDBSCAN Re-Clustering | CPU | ~3-20 s | 2-3 min (Worker mit Progress) |
| Agent-Scoring (pro Cut, 500 Kandidaten) | CPU | — | ≤ 20 ms |
| Memory-Pattern-Re-Aggregation (20 Events) | CPU | — | ~200 ms |

### 8.2 VRAM-Budget

Studio-Brain **belegt kein VRAM**. Alle Enrichment-Steps sind CPU-basiert. Bestehende GPU-Nutzer (SigLIP, RAFT, DEMUCS, beat_this, Gemma) bleiben unangetastet.

### 8.3 Error-Handling-Regeln

**Grundregel:** Kein Analyse-Schritt darf die Library blockieren. Partial-Enrichment ist erlaubt; UI kommuniziert es transparent.

| Fehler | Reaktion |
|---|---|
| SigLIP-Embedding fehlt | Scene in Bucket `misc`, logged, UI-Badge „unclassified" |
| `ai_caption` fehlt | Role-Classifier-Fallback auf motion_score + duration, Confidence ≤ 0.5 |
| HDBSCAN findet nur 1 Cluster | `min_cluster_size` halbiert, retry 1× |
| Gelöschte Scene in `mem_decision` | Audit-Tab zeigt „Clip gelöscht"-Placeholder, kein Crash |
| Stufe 1 lässt 0 Kandidaten übrig | Regel-Aufweichung + `fallback=true` im Rationale |
| Stufe 2 alle Budgets leer | Temporär `max × 2` für diesen Cut, loggen |
| Stufe 3 Penalty → alle Scores ≤ 0 | Nimm Top-1, `forced=true` loggen |
| Fehlende Structure-Segmente | BPM+Energy-Heuristik, `section_inferred=true` |
| SQLite-Lock bei Decision-Insert | 3× Retry + in-memory Queue + Persist nach Run-Ende |

### 8.4 Edge-Cases

1. **Leere Library:** Empty-States, Agent disabled.
2. **Ein Clip:** Clustering übersprungen, Bucket=`all`, Compat-Edges leer.
3. **1-Run-Gedächtnis:** Pattern-Confidence unter Threshold → `w_memory`-Term liefert 0.
4. **Pattern-Reset:** Confirm + Backup nach `storage/memory_backups/`.
5. **Parallel-Runs:** Singleton-Lock im Pacing-Service.
6. **DJ-Mix ohne Structure:** Behandle als 1 Segment, Warnung im Audit.
7. **Run-Rating ohne Einzel-Ratings:** Dämpfungs-Gewicht 0.3× auf alle Decisions dieses Runs.
8. **Schema-Migration Enricher v1→v2:** Neuer Run überschreibt nur Rows mit alter `enricher_version`.

### 8.5 Backup-Strategie

**Neuer Service:** `services/backup_service.py`.
**Trigger:**
- Vor destruktiven Aktionen (Pattern-Reset, Enricher-Version-Wechsel).
- Täglich bei App-Start (wenn `last_backup > 24h`).

**Persistenz:** `storage/backups/pb_studio_YYYY-MM-DD-HH-MM.db`.
**Rolling-Window:** letzte 14 Backups, älteste werden gelöscht.
**Scope:** komplette `pb_studio.db` (einfacher als nur die neuen Tabellen, Disk-Kosten minimal).

### 8.6 Disk-Footprint

| Tabelle | ~Bytes/Row | 5000 Scenes + 50 Runs |
|---|---|---|
| `struct_clip_tags` | 100 | 500 KB |
| `struct_style_bucket` | 5 KB | 60 KB |
| `struct_compat_edge` | 40 | 8 MB |
| `mem_pacing_run` | 200 | 10 KB |
| `mem_decision` | 1 KB | 5 MB |
| `mem_learned_pattern` | 500 | 100 KB |
| `mem_user_feedback_event` | 150 | 300 KB |
| **Total neu** | — | **~14 MB** |

Vernachlässigbar gegen Video-Daten.

---

## 9. Tests, Migration, Rollout

### 9.1 Alembic-Migrationen

Drei neue Migrationen in `database/alembic/versions/` (Template `%%(year)d_%%(month).2d_%%(day).2d_%%(rev)s_%%(slug)s`):

1. `add_struct_layer_tables.py` — `struct_clip_tags`, `struct_style_bucket`, `struct_compat_edge` + Indizes.
2. `add_memory_layer_tables.py` — `mem_pacing_run`, `mem_decision`, `mem_learned_pattern`, `mem_user_feedback_event` + Indizes.
3. `extend_analysis_status_enum.py` — Registry-Update `VIDEO_STEPS += ["structure_enrichment"]`, Data-Migration für bestehende Zeilen.

Jede Migration: **up + down** implementiert. Tests in `tests/db/` gegen leere und gefüllte DB.

### 9.2 Test-Pyramide

**Unit (ms):**
- `tests/enrichment/test_role_classifier.py`
- `tests/enrichment/test_mood_refine.py`
- `tests/enrichment/test_style_bucket.py`
- `tests/enrichment/test_compat_edges.py`
- `tests/pacing/test_stages.py`
- `tests/memory/test_pattern_aggregation.py`
- `tests/memory/test_decision_snapshot.py`

**Integration (s):**
- `tests/integration/test_full_enrichment.py`
- `tests/integration/test_pacing_with_memory.py`
- `tests/integration/test_dj_mix_3h.py` (synthetischer 3h-Audio, assert kein OOM)
- `tests/integration/test_alembic_migrations.py`

**UI (headless `QT_QPA_PLATFORM=offscreen`):**
- `tests/ui/test_studio_brain_window.py`
- `tests/ui/test_feedback_shortcuts.py`

**Golden-Run-Snapshot:** kuratierter 5-min-Mix + 20-Clip-Library; `mem_decision`-Tabelle Byte-identisch pro PR (modulo Timestamps). Deckt Scoring-Regressions.

### 9.3 Implementations-Reihenfolge (kein Feature-Gate, ein Branch)

1. DB + Migrations (Sektion 4).
2. Enrichment-Worker (Sektion 5).
3. Pacing-Agent-Scoring-Erweiterung (Sektion 6).
4. Memory-Recorder + Pattern-Aggregation.
5. Feedback-UI in Timeline (Sektion 7.7).
6. Studio-Brain-Fenster: Tab 1 Struktur.
7. Studio-Brain-Fenster: Tabs 2/3/4 (Gedächtnis / Audit / Steer).
8. Story-Map-Dialog.
9. Backup-Service.
10. pyqtgraph-Dep + Polish.

Merge nach Feature-Complete + Golden-Run grün.

### 9.4 Definition of Done pro Sub-Komponente

- Typed (`mypy --strict`), Black-formatiert.
- ≥ 80% Test-Coverage auf neuen Dateien.
- Up+Down-Migration grün.
- UI-offscreen-Test grün.
- README-Abschnitt + Kurz-Anleitung.

### 9.5 Phase-2-Themen (explizit NICHT in diesem Spec)

- ML-basierter Role-Classifier (ersetzt Regel-Fallback).
- LLM-basierte Style-Bucket-Namensgebung.
- Cross-Projekt-Pattern-Sharing / Transfer-Learning.
- Export des Gedächtnisses als anonymisierter Datensatz.

---

## 10. Offene Fragen (für Phase 2 Recherche)

- **Force-Directed-Layout-Bibliothek für Graph-View:** `networkx` + eigener Renderer, oder gibt es etablierte Qt-Graph-Widgets mit akzeptabler Performance bei 1000+ Knoten?
- **Wilson-Lower-Bound-Parametrisierung:** welches Konfidenz-Niveau (z/alpha) ist sinnvoll, um „2/2 accept" nicht zu früh zu trusten? Literatur-Review.
- **HDBSCAN vs alternative Clustering:** Benchmarks bei 1000+ 1152-dim-Embeddings (UMAP-Preprocessing nötig?).
- **LUFS-Bedeutung für Mood:** gibt es veröffentlichte Mappings Loudness → perceived Mood?
- **Mood-Anchor-Embeddings:** welche Text-Prompts erzeugen robuste SigLIP-Anchor-Vektoren für die 10 Mood-Klassen?
- **DJ-Mix-Onset-Chunking per Structure-Segment:** Best-Practice für Onset-Overlap an Segment-Grenzen (Artefakt-Vermeidung).

---

## 11. Entscheidungsprotokoll

- **Ansatz H (Struktur + Gedächtnis):** alle drei User-Ziele (Qualität / Fehler / Erinnerungen) abgedeckt. A und M allein nicht ausreichend.
- **Auto-Only (kein manuelles Labeln):** User-Entscheidung. Obsidian-Metapher bezieht sich auf UX (Graph, Navigation), nicht auf manuelle Markdown-Pflege.
- **In-App, kein Brain-Bug-Sync:** User-Entscheidung. Studio-Brain ist App-internes Gedächtnis, Brain-Bug bleibt Entwicklungs-Vault.
- **Alle Scoring-Terme in Phase 1:** User-Entscheidung gegen meine ursprüngliche Phasen-Empfehlung. Grund: konsistenter Decision-Context-Snapshot von Run #1.
- **CPU-Only Enrichment:** bewusst gewählt, damit GPU-Budget frei bleibt (SigLIP/RAFT/Gemma/DEMUCS belegen es schon).
- **Feedback-UI in Timeline, nicht im Studio-Brain:** damit Feedback im Flow passiert, nicht als separater Schritt.
- **pyqtgraph als neue Dependency:** verifiziert, dass weder PyQtGraph noch matplotlib installiert sind; pyqtgraph ist lightweight (~1 MB, MIT).
- **sklearn.cluster.HDBSCAN statt hdbscan-package:** verifiziert, dass `scikit-learn==1.8.0` bereits installiert ist und HDBSCAN enthält — keine neue Dependency.

---

**Ende Spec.**
