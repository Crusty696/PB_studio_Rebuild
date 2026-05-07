# Phase 3 Blueprint — Brain-Core (Beta-Bernoulli + Hierarchical Backoff)

> **🟢 STATUS 2026-05-05: PHASE 3 IST IMPLEMENTIERT + 112/112 PYTEST GRÜN.**
>
> Alle 9 Code-Files + Test-Datei existieren bereits unter `services/brain_v3/`
> aus einem vorherigen Build-Lauf (User-Story: "Cowork-Session ist übers
> Ziel hinausgeschossen"). Die Files wurden gegen diesen Blueprint verifiziert
> → 0 Spec-Drift. Tests live grün auf GTX 1060.
>
> **Falls du diesen Blueprint von vorne als 'build-from-scratch'-Brief liest:
> STOP.** Lies stattdessen Synthesis-Doc:
> `docs/superpowers/synthesis/2026-05-05-brain-v3-phase3-completion.md`.
>
> Dieser Blueprint bleibt als **API-Spezifikation** stehen für künftige
> Refactorings, Code-Reviews oder Replacement-Implementierungen.

## 1. Ziel + Erfolgsdefinition

**Ziel:** Lern-Algorithmus produktiv. Mock-Klicks → Posterior-Konvergenz
nachweisbar. Hierarchical Backoff über 5 Levels funktional. Atomic
102-Bucket-Update pro Klick in einer Transaktion.

**Erfolg = wahr wenn:** Alle 8 Module unter `services/brain_v3/` (siehe
Sektion 4) implementiert + alle Tests aus Sektion 7 grün auf GTX 1060 +
Synthesis-Doc geschrieben.

**Aufwand-Schätzung:** 3–5 Tage (CPU-Logic + SQLite, keine GPU).

---

## 2. Voraussetzungen

| Voraussetzung | Quelle | Status |
|---|---|---|
| Phase 0 (GPU-Coexistenz-Spike) DONE | `outputs/spike_brain_v3_gpu/20260503_115926/` | ✓ |
| Phase 1 (Datenseite, Schemas) DONE | `services/brain_v3/{hashing,paths,schemas,audio,video}/` | ✓ |
| Phase 2 (Storage, Embedder, Background-Queue) DONE | `services/brain_v3/{storage,gpu_serializer,background_queue}.py` | ✓ |
| `BRIDGE_AXES` 17 Achsen konzeptionell definiert | `05_BRIDGE_AXES.md` | ✓ |
| 6 Kontext-Slots quantisiert | `05_BRIDGE_AXES.md` | ✓ |
| Cold-Start-Defaults aus TriggerSettings | `05_BRIDGE_AXES.md` | ✓ |

---

## 3. Architektur

```text
services/brain_v3/
├── cold_start.py              ←── BRIDGE_AXES + COLD_START_DEFAULTS dict
├── context_resolver.py        ←── CutContext dataclass + 6 Slots + context_keys()
├── bridge_dimensions.py       ←── BridgeDimensions: compute(axis, candidate, ctx) → [0,1]
├── weight_store.py            ←── Beta-Bernoulli: get_posterior_mean + Backoff
├── feedback_logger.py         ←── Atomic 102-Bucket-Update pro Klick
├── scorer.py                  ←── kombiniert Bridge × Weight → Final-Score
└── storage/
    ├── brain_store.py         ←── öffnet weights.db + patterns.db + embedding_cache.db
    └── sql_migrations/
        ├── weights/001_initial.sql
        └── patterns/001_initial.sql
```

**Daten-Fluss:**

```text
ContextResolver (6 Slots → 6 Backoff-Keys)
                        │
                        ▼
WeightStore.get_posterior_mean(axis, keys)  ←──  weights.db (axis_weights)
                        │
                        ▼
Scorer:  bridge_value × posterior_weight → sub_score pro Achse
                        │
                        ▼
FeedbackLogger.log_feedback(rating, keys)  →  weights.db (102 Bucket-UPSERTs)
```

---

## 4. Datei-für-Datei-Spezifikation

### 4.1 `services/brain_v3/cold_start.py`

```python
# Konstanten + Helper, KEINE Klasse.
BRIDGE_AXES: tuple[str, ...] = (
    # 10 Audio (aus TriggerSettings):
    "beat_weight", "onset_weight", "kick_weight", "snare_weight",
    "hihat_weight", "energy_weight", "energy_threshold",
    "onset_sensitivity", "min_clip_length", "max_clip_length",
    # 7 Video (NEU):
    "motion_match_weight", "scene_cut_weight", "brightness_match_weight",
    "color_temp_match_weight", "pace_match_weight",
    "semantic_match_weight", "mood_match_weight",
)
COLD_START_DEFAULTS: dict[str, float] = { ... }  # 17 Werte, siehe 05_BRIDGE_AXES.md

def get_default(axis: str) -> float: ...
```

**Asserts:**
- `len(BRIDGE_AXES) == 17`
- `set(COLD_START_DEFAULTS) == set(BRIDGE_AXES)`

### 4.2 `services/brain_v3/context_resolver.py`

```python
# Frozen dataclass mit Validation
@dataclass(frozen=True)
class CutContext:
    audio_section_type: str = "verse"      # validate gegen VALID_SECTIONS
    audio_subtrack_position: str = "middle"  # validate gegen VALID_SUBPOS
    audio_energy_level: str = "medium"     # validate gegen VALID_ENERGY
    audio_mood: str = "neutral"            # validate gegen VALID_MOOD
    video_motion_class: str = "medium"     # validate gegen VALID_MOTION
    video_pace_class: str = "medium"       # validate gegen VALID_PACE
    raw_audio_features: dict = field(default_factory=dict)  # für Bridge-Berechnung
    raw_video_features: dict = field(default_factory=dict)

def context_keys(cut: CutContext) -> list[str]:
    """6 Backoff-Keys, Level 0..5, aufsteigend in Spezifität."""

def quantize_tertile(value, p33, p66, classes=("low","medium","high")) -> str: ...
def quantize_subtrack_position(time_s, sub_start_s, sub_end_s) -> str: ...
```

**Backoff-Key-Schema** (verbindlich):
```text
Level 0: ""
Level 1: "section={section}|"
Level 2: "section=...|mood={mood}|"
Level 3: "section=...|mood=...|motion={motion}|"
Level 4: "section=...|mood=...|motion=...|energy={energy}|"
Level 5: "section=...|mood=...|motion=...|energy=...|pace={pace}|subpos={subpos}|"
```

### 4.3 `services/brain_v3/storage/sql_migrations/weights/001_initial.sql`

```sql
CREATE TABLE IF NOT EXISTS axis_weights (
    axis           TEXT NOT NULL,
    context_level  INTEGER NOT NULL CHECK(context_level BETWEEN 0 AND 5),
    context_key    TEXT NOT NULL,
    positive_count REAL NOT NULL DEFAULT 0,
    negative_count REAL NOT NULL DEFAULT 0,
    last_updated   TEXT NOT NULL,
    PRIMARY KEY (axis, context_level, context_key)
);
CREATE INDEX IF NOT EXISTS idx_axis_level ON axis_weights(axis, context_level);
```

### 4.4 `services/brain_v3/storage/sql_migrations/patterns/001_initial.sql`

```sql
CREATE TABLE IF NOT EXISTS pattern_correlations (
    audio_profile_hash TEXT NOT NULL,
    video_profile_hash TEXT NOT NULL,
    positive_count     INTEGER NOT NULL DEFAULT 0,
    negative_count     INTEGER NOT NULL DEFAULT 0,
    contexts_json      TEXT,
    last_seen          TEXT NOT NULL,
    PRIMARY KEY (audio_profile_hash, video_profile_hash)
);
CREATE INDEX IF NOT EXISTS idx_audio_profile ON pattern_correlations(audio_profile_hash);
CREATE INDEX IF NOT EXISTS idx_video_profile ON pattern_correlations(video_profile_hash);
```

### 4.5 `services/brain_v3/storage/brain_store.py`

```python
@dataclass(frozen=True)
class BrainStoreStats:
    weights_rows: int
    patterns_rows: int
    embedding_cache_rows: int
    weights_db_size_bytes: int
    patterns_db_size_bytes: int
    embedding_cache_db_size_bytes: int

class BrainStore:
    def __init__(self, weights_path=None, patterns_path=None):
        # Lädt Pfade aus services.brain_v3.paths, ruft migrate() für beide DBs.
    def open_weights(self) -> sqlite3.Connection: ...
    def open_patterns(self) -> sqlite3.Connection: ...
    def stats(self) -> BrainStoreStats: ...
    def reset(self, also_embedding_cache: bool = False) -> None: ...
    def checkpoint_all(self, mode: str = "TRUNCATE") -> None: ...
```

### 4.6 `services/brain_v3/weight_store.py`

```python
MIN_CONFIDENT_SAMPLES = 10

@dataclass(frozen=True)
class AlphaBeta:
    alpha: float
    beta: float
    @property
    def n_samples(self) -> float: return self.alpha + self.beta
    @property
    def posterior_mean(self) -> float: return (self.alpha + 1) / (self.alpha + self.beta + 2)
    @property
    def variance(self) -> float: ...  # α·β / ((α+β)² · (α+β+1))

class WeightStore:
    def __init__(self, db_path): ...  # öffnet Connection lazy
    def close(self) -> None: ...
    def get_alpha_beta(self, axis, level, key) -> Optional[AlphaBeta]: ...
    def get_posterior_mean(self, axis, context_keys_by_level) -> float:
        # Spezifischster Level zuerst, ≥10 Samples → return
        # Fallback: cold_start.get_default(axis)
    def get_variance_for_smart_sampling(self, axis, context_keys_by_level) -> float: ...
    def update(self, axis, level, key, alpha_delta, beta_delta) -> None: ...  # UPSERT
    def total_clicks(self) -> float: ...
    def top_buckets(self, n=5, by="positive") -> list[dict]: ...
    def cold_start_status(self) -> dict[str, int]: ...  # confident_axes/cold_start_axes
```

### 4.7 `services/brain_v3/feedback_logger.py`

```python
RATING_MAP: dict[str, tuple[float, float]] = {
    "perfect":   (2.0, 0.0),
    "fits":      (1.0, 0.0),
    "not_quite": (0.0, 1.0),
    "no_match":  (0.0, 2.0),
}

class FeedbackLogger:
    def __init__(self, weights: WeightStore): ...
    def log_feedback(self, rating: str, context_keys_by_level: list[str]) -> dict:
        # Validation: rating in RATING_MAP, len(keys) == 6
        # Atomic: BEGIN; for axis in BRIDGE_AXES: for level, key in enumerate(keys):
        #   UPSERT axis_weights ...
        # COMMIT (oder ROLLBACK on Exception)
        # Returns: {rating, alpha_delta, beta_delta, n_buckets_updated=102}
```

### 4.8 `services/brain_v3/bridge_dimensions.py`

```python
@dataclass
class ClipCandidate:
    clip_id: str
    duration_s: float
    motion_score: float = 0.5
    brightness: float = 0.5
    saturation: float = 0.5
    color_temp: float = 0.0  # -1..+1
    embedding: Optional[np.ndarray] = None  # 768-dim SigLIP-2
    mood_tags: list[str] = field(default_factory=list)
    style_tags: list[str] = field(default_factory=list)

class BridgeDimensions:
    def compute(self, axis: str, candidate: ClipCandidate, cut_context: CutContext) -> float:
        # Returns Wert in [0, 1]. Dispatch auf _compute_<axis>-Methode.
        # Fallback: 0.5. Exception → log + 0.5 (kein Crash).
    def compute_all(self, candidate, cut_context) -> dict[str, float]: ...
```

**17 _compute_*-Methoden** — vereinfachte Phase-3-Implementation:
- Audio-Achsen: lesen aus `ctx.raw_audio_features` (TriggerSettings-ähnlich)
- Video-Achsen: kombinieren `candidate.motion_score/brightness/...` mit Audio-Kontext

### 4.9 `services/brain_v3/scorer.py`

```python
@dataclass
class ScoredCandidate:
    candidate: ClipCandidate
    final_score: float
    brain_v3_scores: dict[str, float] = field(default_factory=dict)

class Scorer:
    def __init__(self, bridge: BridgeDimensions, weights: WeightStore): ...
    def score(self, candidate, cut_context) -> ScoredCandidate:
        # final_score = mean(bridge_value × weight für alle 17 Achsen)
    def score_all(self, candidates, cut_context) -> list[ScoredCandidate]:
        # sortiert absteigend nach final_score
```

---

## 5. SQL-Migrations

Reihenfolge:
1. `weights/001_initial.sql` (axis_weights + idx_axis_level)
2. `patterns/001_initial.sql` (pattern_correlations + 2 Indizes)

Beide via `services.brain_v3.storage.migration_runner.migrate(db_path, mig_dir)`.
Idempotent (PRAGMA user_version).

---

## 6. App-Eingriffspunkte

**KEINE in Phase 3.** Phase 3 ist rein V3-isoliert. App-Pacing-Hooks
kommen in Phase 4.

---

## 7. Test-Spezifikation

Datei: `tests/test_services/test_brain_v3_brain_core.py`

**Mindestens diese Tests** (alle live-verifiziert via `run_pytest_brain_v3.bat`):

### cold_start (4 Tests)
- `test_bridge_axes_count_is_17`
- `test_cold_start_covers_all_axes`
- `test_get_default_known_axis` (kick_weight = 1.2, motion_match = 0.5)
- `test_get_default_unknown_axis_raises` → KeyError

### context_resolver (7 Tests)
- `test_cut_context_default_values_validate`
- `test_cut_context_invalid_section_raises` → ValueError
- `test_cut_context_invalid_mood_raises` → ValueError
- `test_context_keys_returns_six_levels`
- `test_context_keys_are_unique_per_context`
- `test_quantize_tertile` (low/medium/high)
- `test_quantize_subtrack_position` (start/middle/end)

### weight_store / Beta-Bernoulli (8 Tests)
- `test_alpha_beta_posterior_mean_cold_start` → 0.5
- `test_alpha_beta_posterior_mean_strong_positive` → 21/22
- `test_alpha_beta_variance_decreases_with_more_data`
- `test_get_posterior_mean_cold_start_returns_default`
- `test_get_posterior_mean_after_clicks_uses_level_0`
- `test_backoff_finds_specific_when_confident` (Level 1 ≥10 Samples → wins)
- `test_backoff_falls_back_when_specific_not_confident` (Level 1 <10 → Level 0)
- `test_get_posterior_mean_unknown_axis_raises` → ValueError

### weight_store / Diagnostics (3 Tests)
- `test_total_clicks_grows_with_updates`
- `test_top_buckets_returns_strongest_positive`
- `test_cold_start_status_one_axis_confident` (1 von 17 verlässt Cold-Start)

### feedback_logger (7 Tests)
- `test_rating_map_completeness` (4 Ratings, Plan-Doc-konform)
- `test_log_feedback_updates_85_buckets` (17 × 6 = 102 — Phase 3 verwendet 6 Levels statt 5 wie ursprünglich; das ist Plan-Doc-Update durch Phase 3)
- `test_log_feedback_perfect_increments_alpha_only` (kick_weight L0: α=2.0, β=0)
- `test_log_feedback_no_match_increments_beta_only`
- `test_log_feedback_invalid_rating_raises`
- `test_log_feedback_wrong_keys_length_raises`
- `test_log_feedback_atomic_rollback_on_error` (DROP TABLE → Rollback verifiziert)

### bridge_dimensions (5 Tests)
- `test_bridge_compute_returns_in_range` (alle 17 Achsen → [0,1])
- `test_bridge_compute_all_returns_17`
- `test_bridge_motion_match_perfect_alignment` (motion=energy → 1.0)
- `test_bridge_unknown_axis_raises`
- `test_bridge_semantic_match_with_aligned_embedding` (Cosine=1 → 1.0)

### scorer (2 Tests)
- `test_scorer_returns_scored_candidate`
- `test_scorer_score_all_sorts_descending`

### brain_store (3 Tests)
- `test_brain_store_initializes_three_dbs`
- `test_brain_store_reset_clears_weights_and_patterns`
- `test_brain_store_reset_keeps_embedding_cache_by_default`

### Integration (1 Test)
- `test_integration_clicks_change_posterior` (15 perfect → 30/32, dann
  15 no_match → 31/62 ≈ 0.5)

**Erwartete Test-Anzahl: ~50** (Mindest-Cover, mehr ist erlaubt).

**Wichtige Subtilität:** Cold-Start-Defaults wie `kick_weight=1.2` sind in
TriggerSettings-Skala (0–2). Posterior-Mean ist in (0, 1). Test darf nicht
direkt "Cold-Start vs Posterior-Mean" vergleichen — sondern Posterior-
Verschiebung durch Klick-Vorzeichen.

---

## 8. Definition of Done

```text
✓ Alle 8 Module unter services/brain_v3/ existieren
✓ Beide SQL-Migrations laufen idempotent
✓ ~50 pytest-Tests grün auf GTX 1060 (live, nicht nur statisch)
✓ Mock-Klick-Loop verändert Posterior nachweisbar (Integration-Test)
✓ Atomic-102-Bucket-Update verifiziert via Rollback-Test
✓ Backoff-Lookup findet konfidentes Bucket wenn vorhanden, sonst Cold-Start
✓ Reset löscht weights+patterns, embedding_cache bleibt
✓ run_pytest_brain_v3.bat erweitert um test_brain_v3_brain_core.py
✓ Synthesis-Doc unter docs/superpowers/synthesis/ angelegt
```

---

## 9. Risiken + Mitigationen

| Risiko | Mitigation |
|---|---|
| Atomic-Update bricht halbweg ab → inkonsistente DB | BEGIN…COMMIT mit ROLLBACK in except. Test mit DROP TABLE-Provokation. |
| Cold-Start-Defaults vs. Posterior-Mean-Skala-Mismatch | Doku in 05_BRIDGE_AXES + scorer.py klar machen: Posterior überschreibt Default nur wenn ≥10 Samples |
| Backoff-Lookup zu langsam bei vielen Achsen × Levels | 17 × 6 = 102 SELECTs pro Cut. Bei 100 Cuts/Pacing = 10 200 SELECTs. WAL + cache_size=-32000 sollte <500 ms halten. Profiling in Phase 4. |
| C-Extension `sqlite3.Connection.execute` ist read-only → monkeypatch geht nicht | Atomic-Test via DROP TABLE statt Mock. |

---

## 10. Verifikations-Strategie

- **Unit-Tests:** ~50 Tests in `test_brain_v3_brain_core.py`
- **Integration-Test:** `test_integration_clicks_change_posterior` — Mock-Klick-Loop
- **Live-Lauf:** `run_pytest_brain_v3.bat` doppelklicken auf User-Maschine
- **Output-Check:** `outputs/pytest_brain_v3_results.txt` muss 100 % grün zeigen
  (alte Phase-1+2-Tests bleiben grün, plus ~50 neue)

---

## 11. Reihenfolge der Implementation

```text
1. cold_start.py + Test (5 Min)
2. context_resolver.py + Test (15 Min)
3. SQL-Migrations weights + patterns (5 Min)
4. brain_store.py + Test (15 Min)
5. weight_store.py (Beta-Bernoulli + Backoff) + Test (45 Min)
6. feedback_logger.py (Atomic-85-Update) + Test (30 Min)
7. bridge_dimensions.py (17 Achsen-Berechner) + Test (45 Min)
8. scorer.py (Bridge × Weight) + Test (15 Min)
9. run_pytest_brain_v3.bat erweitern + alle Tests laufen lassen
10. Synthesis-Doc schreiben

Total: ~3-4 Stunden reine Code-Zeit + Test-Verifikation.
```

---

## Hinweis für Claude Code

In `services/brain_v3/` liegen bereits **Referenz-Implementierungen**
für alle 8 Module aus einem vorherigen Build-Versuch. Diese können als
**Vorlage** dienen, sind aber nicht final verifiziert. Du darfst sie
überschreiben oder als Startpunkt nutzen. Tests sind in
`tests/test_services/test_brain_v3_brain_core.py` schon angelegt mit
~50 Tests (3 davon Test-Logik-Bugs hatten, sind im Code dokumentiert).
