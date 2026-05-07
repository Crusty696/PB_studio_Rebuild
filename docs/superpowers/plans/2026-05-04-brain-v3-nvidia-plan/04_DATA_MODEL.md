# 04 — Datenmodell (Brain V3, NVIDIA)

## Daten-Schichtung

| Store | Pfad | Anzahl Files | Lebenszyklus | Phase |
|---|---|---|---|---|
| Projekt-Store | `<Projekt>/brain_v3/embeddings.db` | 1 | mit Projekt löschbar | 2 ✓ |
| Projekt-Store | `<Projekt>/brain_v3/state.db` | 1 | mit Projekt löschbar | 4 |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\weights.db` | 1 | app-global | 3 |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\patterns.db` | 1 | app-global | 3 |
| Hirn-Store | `%APPDATA%\PB_Studio\brain_v3\embedding_cache.db` | 1 | app-global | 2 ✓ |

**Gesamt: 5 SQLite-Files**, alle mit WAL + identischem PRAGMA-Setup.
Pfade implementiert in `services/brain_v3/paths.py` (Phase 1 ✓), strikt
getrennt von V1/V2-Pfaden (`%APPDATA%\PB_Studio\` direkt).

Embedding-Files (`.npy`) liegen physisch unter
`%APPDATA%\PB_Studio\brain_v3\embeddings\<media_type>\<safe_model>__<safe_ver>\<2hex>\<hash>.npy`
— nested-Pfad-Konvention verhindert >10k Files in einem Verzeichnis (NTFS-
Performance-Best-Practice).

---

## PRAGMA-Setup (jede Connection)

Implementiert in [`services/brain_v3/storage/sqlite_init.py`](../../../services/brain_v3/storage/sqlite_init.py) ✓:

```python
PRAGMA_INIT: tuple[str, ...] = (
    "PRAGMA journal_mode = WAL",         # persistent — einmal gesetzt, bleibt
    "PRAGMA synchronous = NORMAL",       # WAL-sicher + schneller als FULL
    "PRAGMA temp_store = MEMORY",        # temp tables im RAM
    "PRAGMA cache_size = -32000",        # 32 MB pro Connection
    "PRAGMA mmap_size = 268435456",      # 256 MB memory-mapped I/O
    "PRAGMA foreign_keys = ON",          # Referential Integrity
    "PRAGMA busy_timeout = 5000",        # 5 s warten bei Lock-Contention
)
```

**Begründung WAL + NORMAL** ([SQLite-Doc](https://www.sqlite.org/wal.html)):
- WAL erlaubt concurrent Reader während Writer arbeitet
- `synchronous = NORMAL` ist im WAL-Mode crash-sicher (im Gegensatz zu
  DELETE-Mode, wo NORMAL Daten verlieren kann)
- `synchronous = FULL` wäre 2–3× langsamer ohne Sicherheitsgewinn im WAL

**Verifiziert durch** `tests/test_services/test_brain_v3_storage_cache.py::test_init_connection_sets_wal_mode`.

---

## Schema 1: Hirn-Store — `weights.db` (Phase 3, TODO)

```sql
-- Datei: services/brain_v3/storage/sql_migrations/weights/001_initial.sql
-- Zweck: Gelernte Achsen-Gewichte mit hierarchischer Konditionierung
-- Anwendung: Beta-Bernoulli-Update pro Klick auf 5 Levels gleichzeitig

CREATE TABLE axis_weights (
    axis           TEXT NOT NULL,          -- z.B. "kick_weight", "motion_match_weight"
    context_level  INTEGER NOT NULL,       -- 0..5 (0=global, 5=alle 6 Slots)
    context_key    TEXT NOT NULL,          -- z.B. "section=drop|mood=dark|motion=high"
    positive_count REAL NOT NULL DEFAULT 0,-- α (REAL wegen 2.0/1.0-Gewichtung)
    negative_count REAL NOT NULL DEFAULT 0,-- β
    last_updated   TEXT NOT NULL,          -- ISO-8601 Timestamp
    PRIMARY KEY (axis, context_level, context_key)
);

CREATE INDEX idx_axis_level ON axis_weights(axis, context_level);
```

**Posterior-Mean-Berechnung im Code:**
```python
# Beta-Bernoulli mit Laplace-Smoothing
posterior_mean = (alpha + 1) / (alpha + beta + 2)

# Varianz für Smart-Sampling
variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
```

**Erwartete Größe:** 17 Achsen × 5 Levels × ~300 unique context_keys = ~25.5 k
Zeilen nach 10 k Klicks. Plus α/β-Werte mit Updates → DB-Datei ~5 MB.

---

## Schema 2: Hirn-Store — `patterns.db` (Phase 3, TODO)

```sql
-- Datei: services/brain_v3/storage/sql_migrations/patterns/001_initial.sql
-- Zweck: Audio↔Video Profil-Korrelationen projektübergreifend

CREATE TABLE pattern_correlations (
    audio_profile_hash TEXT NOT NULL,
    video_profile_hash TEXT NOT NULL,
    positive_count     INTEGER NOT NULL DEFAULT 0,
    negative_count     INTEGER NOT NULL DEFAULT 0,
    contexts_json      TEXT,                   -- JSON-Array beobachteter Kontexte
    last_seen          TEXT NOT NULL,
    PRIMARY KEY (audio_profile_hash, video_profile_hash)
);

CREATE INDEX idx_audio_profile ON pattern_correlations(audio_profile_hash);
CREATE INDEX idx_video_profile ON pattern_correlations(video_profile_hash);
```

**Profil-Hash-Bildung:** quantisierte Brücken-Features
(z.B. `motion=high|brightness=mid|tempo_class=fast`) → SHA1-Hash → 16-stellig.

---

## Schema 3: Hirn-Store — `embedding_cache.db` (Phase 2 ✓ implementiert)

Implementiert in [`services/brain_v3/storage/sql_migrations/embedding_cache/001_initial.sql`](../../../services/brain_v3/storage/sql_migrations/embedding_cache/001_initial.sql):

```sql
CREATE TABLE IF NOT EXISTS media_embedding_index (
    media_hash      TEXT PRIMARY KEY,
    media_type      TEXT NOT NULL CHECK(media_type IN ('audio', 'video')),
    embedding_path  TEXT NOT NULL,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    file_size_bytes INTEGER
);

CREATE INDEX IF NOT EXISTS idx_media_embedding_model
    ON media_embedding_index(model_name, model_version);
```

**Sibling-Tabelle (Phase 1 App-Sync, Plan-Amendment 2026-05-05)** in
derselben `embedding_cache.db` via Migration
[`002_media_hashes.sql`](../../../services/brain_v3/storage/sql_migrations/embedding_cache/002_media_hashes.sql):

```sql
CREATE TABLE IF NOT EXISTS media_hashes (
    media_hash       TEXT PRIMARY KEY,
    media_type       TEXT NOT NULL CHECK(media_type IN ('audio', 'video')),
    source_path      TEXT NOT NULL,
    file_size_bytes  INTEGER NOT NULL,
    computed_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_hashes_type ON media_hashes(media_type);
CREATE INDEX IF NOT EXISTS idx_media_hashes_path ON media_hashes(source_path);
```

Persistiert sha256-Hashes direkt beim Audio/Video-Import (Phase 1
App-Sync), bevor Phase 2 Embeddings rechnet. Persistenz-Layer:
[`MediaHashRegistry`](../../../services/brain_v3/storage/media_hash_registry.py).
Wird vom [`BrainV3HashingWorker`](../../../workers/brain_v3_hashing.py)
nach `FolderImportWorker.finished` aufgerufen. Cache-Hit-Pfad
(`is_new=False`) verhindert doppelte DB-Eintraege bei Re-Import.

**Datei-Zaehlung bleibt bei 5 SQLite-Files** — `media_hashes` ist
Sibling in `embedding_cache.db`, kein neues File.

**Embedding-Files** liegen physisch in
`%APPDATA%\PB_Studio\brain_v3\embeddings\<media_type>\<safe_model>__<safe_ver>\<2hex>\<hash>.npy`,
nicht in der DB selbst. DB ist nur Index. Format: `.npy` (numpy binary).

**Verifiziert durch** `tests/test_services/test_brain_v3_storage_cache.py`
(15 Tests, inkl. Round-Trip, Model-Version-Mismatch, Path-Separation).

**Real-Daten Phase-2-Spike 20260504_145214:**
- 100 % Re-Import-Hit-Rate für 3 Audio + 3 Video Files in 0.04 s + 0.08 s
- Plan-Doc 06 Phase 2 DoD "Cache-Hit-Rate ≥95%" **MET** ✓

---

## Schema 4: Projekt-Store — `embeddings.db` (Phase 2 ✓ implementiert)

Implementiert in [`services/brain_v3/storage/sql_migrations/embeddings_project/001_initial.sql`](../../../services/brain_v3/storage/sql_migrations/embeddings_project/001_initial.sql):

```sql
-- 3-Tier Audio-Hierarchie (mix > section > window)
CREATE TABLE IF NOT EXISTS audio_units (
    id            INTEGER PRIMARY KEY,
    parent_id     INTEGER,
    level         TEXT NOT NULL CHECK(level IN ('mix', 'section', 'window')),
    media_id      INTEGER NOT NULL,
    media_hash    TEXT NOT NULL,
    start_time    REAL NOT NULL,
    end_time      REAL NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (parent_id) REFERENCES audio_units(id)
);

CREATE INDEX IF NOT EXISTS idx_audio_media ON audio_units(media_id, level);
CREATE INDEX IF NOT EXISTS idx_audio_hash  ON audio_units(media_hash);

-- CLAP Audio-Embeddings: 512-dim (sqlite-vec virtual table)
CREATE VIRTUAL TABLE IF NOT EXISTS audio_embeddings USING vec0(
    embedding FLOAT[512]
);

-- 2-Tier Video-Hierarchie (clip > scene), frame-level opt-in
CREATE TABLE IF NOT EXISTS video_units (
    id            INTEGER PRIMARY KEY,
    parent_id     INTEGER,
    level         TEXT NOT NULL CHECK(level IN ('clip', 'scene', 'frame')),
    media_id      INTEGER NOT NULL,
    media_hash    TEXT NOT NULL,
    start_time    REAL NOT NULL,
    end_time      REAL NOT NULL,
    motion_score  REAL,
    brightness    REAL,
    saturation    REAL,
    color_temp    REAL,
    metadata_json TEXT,
    FOREIGN KEY (parent_id) REFERENCES video_units(id)
);

CREATE INDEX IF NOT EXISTS idx_video_media ON video_units(media_id, level);
CREATE INDEX IF NOT EXISTS idx_video_hash  ON video_units(media_hash);

-- SigLIP-2 Video-Embeddings: 768-dim
CREATE VIRTUAL TABLE IF NOT EXISTS video_embeddings USING vec0(
    embedding FLOAT[768]
);
```

**KNN-Beispiel-Query:**
```sql
SELECT u.id, u.media_id, e.distance
FROM video_embeddings e
JOIN video_units u ON u.id = e.rowid
WHERE e.embedding MATCH ?  -- query-blob (little-endian float32)
  AND k = ?                -- top-K (sqlite-vec API)
  AND u.level = 'scene'
ORDER BY e.distance;
```

**sqlite-vec-Quelle:** [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) —
pure-C Extension, vec0 virtual table, MATCH-Syntax mit `k = N` Parameter.

**Verifiziert durch** `tests/test_services/test_brain_v3_storage_repo.py`
(6 Tests inkl. KNN-Reihenfolge, Level-Filter, Dim-Mismatch-Validation).

**Real-Daten Phase-2-Spike 20260504_145231:**
- Insert 16k Audio-Vektoren in 771 s (48.2 ms/vec)
- Insert 16k Video-Vektoren in 808 s (50.5 ms/vec)
- KNN median Audio: 63 ms, Video: 108 ms (siehe `07_RISKS.md` R18)

---

## Schema 5: Projekt-Store — `state.db` (Phase 4, TODO)

```sql
-- Datei: services/brain_v3/storage/sql_migrations/state/001_initial.sql
-- Zweck: Timeline + Pacing-Konfig + Roh-Klick-Events

CREATE TABLE timelines (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    audio_clip_id INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    config_json   TEXT,                      -- Pacing-Config (in-process, kein REST-Schema) serialisiert
    is_current    INTEGER DEFAULT 0
);

CREATE TABLE timeline_cuts (
    id                INTEGER PRIMARY KEY,
    timeline_id       INTEGER NOT NULL,
    position_idx      INTEGER NOT NULL,
    clip_id           TEXT NOT NULL,
    start_time        REAL NOT NULL,
    end_time          REAL NOT NULL,
    clip_start        REAL DEFAULT 0,
    trigger_type      TEXT,
    trigger_strength  REAL,
    segment_type      TEXT,
    brain_v3_scores_json TEXT,               -- 17 Sub-Scores zum Cut-Zeitpunkt
    metadata_json     TEXT,
    FOREIGN KEY (timeline_id) REFERENCES timelines(id) ON DELETE CASCADE
);

CREATE TABLE feedback_events (
    id            INTEGER PRIMARY KEY,
    cut_id        INTEGER NOT NULL,
    rating        TEXT NOT NULL,             -- 'perfect'|'fits'|'not_quite'|'no_match'
    alpha_delta   REAL NOT NULL,             -- 2.0 | 1.0 | 0 | 0
    beta_delta    REAL NOT NULL,             -- 0   | 0   | 1.0 | 2.0
    context_keys_json TEXT NOT NULL,         -- 5 Backoff-Keys serialisiert
    timestamp     TEXT NOT NULL,
    FOREIGN KEY (cut_id) REFERENCES timeline_cuts(id) ON DELETE CASCADE
);

CREATE INDEX idx_feedback_timestamp ON feedback_events(timestamp);
```

**Wichtig:** Spalte heißt `brain_v3_scores_json` (nicht `brain_scores_json`),
damit V1/V2-Code keine Cross-Read-Verwirrung bekommt.

---

## Migration-Runner

Implementiert in [`services/brain_v3/storage/migration_runner.py`](../../../services/brain_v3/storage/migration_runner.py) ✓:

```python
def migrate(db_path: Path | str, migrations_dir: Path | str) -> int:
    """Lightweight Migrations via PRAGMA user_version.

    Args:
        db_path: Ziel-DB-Datei.
        migrations_dir: Verzeichnis mit nummerierten *.sql Dateien
                        z.B. 001_initial.sql, 002_add_index.sql

    Returns:
        Hoechste angewandte user_version nach Lauf.
    """
    # Atomar pro Migration: BEGIN; <sql>; PRAGMA user_version=N; COMMIT;
    # Bei Fehler: ROLLBACK + RuntimeError mit Script-Name.
```

**Verifiziert durch:**
- `test_brain_v3_storage_cache.py::test_migrate_applies_scripts_in_order`
- `test_brain_v3_storage_cache.py::test_migrate_is_idempotent`
- `test_brain_v3_storage_cache.py::test_migrate_failed_script_rolls_back`

**Verzeichnis-Struktur (Stand Phase 2):**
```text
services/brain_v3/storage/sql_migrations/
├── embedding_cache/
│   └── 001_initial.sql                    ✓
├── embeddings_project/
│   └── 001_initial.sql                    ✓
├── weights/                               (TODO Phase 3)
│   └── 001_initial.sql
├── patterns/                              (TODO Phase 3)
│   └── 001_initial.sql
└── state/                                 (TODO Phase 4)
    └── 001_initial.sql
```

---

## Backup-Strategie (Phase 6, TODO)

```python
# Datei (TODO): services/brain_v3/storage/backup.py
# Mechanismus: VACUUM INTO (atomar, online, konsistent)

def backup_brain_v3_store(brain_dir: Path, backup_dir: Path) -> Path:
    """Erstellt atomares Backup aller V3-Hirn-Store-DBs.

    VACUUM INTO ist atomar und konsistent während WAL-Writes.
    Sicherer als File-Copy, da keine Race-Condition mit aktiven Writern.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"brain_v3_backup_{timestamp}"
    target.mkdir(parents=True, exist_ok=True)

    for db_file in ("weights.db", "patterns.db", "embedding_cache.db"):
        src = brain_dir / db_file
        if not src.exists():
            continue
        dst = target / db_file
        conn = sqlite3.connect(src)
        try:
            conn.execute("VACUUM INTO ?", (str(dst),))
        finally:
            conn.close()

    return target
```

**Empfohlene Trigger:**
- Wöchentlich automatisch via Background-Task (Phase 6)
- Manuell vor Schema-Migrations
- Manuell vor App-Update

**External-Verify:** [SQLite VACUUM-Doc](https://www.sqlite.org/lang_vacuum.html)
bestätigt VACUUM INTO ist online + transaktional + ergibt vollständiges Backup.

---

## Datenfluss bei Klick (Phase 4 Beispiel)

```text
1. UI ruft (in-process) BrainV3Service.feedback(BrainV3FeedbackRequest(
                                  cut_id=42, rating="perfect"))
   │
2. BrainV3Service liest cut_id=42 aus state.db → brain_v3_scores_json
   │
3. ContextResolver baut 5 Kontext-Keys (Level 0..5)
   │
4. FeedbackLogger.log() — atomar in einer Transaktion:
   ├─ Insert feedback_events (state.db) → Klick-Roh-Log
   └─ Update axis_weights (weights.db)
       für jede der 17 Achsen × 5 Levels:
         INSERT INTO axis_weights ... ON CONFLICT(axis, context_level, context_key)
         DO UPDATE SET positive_count = positive_count + alpha_delta,
                       negative_count = negative_count + beta_delta,
                       last_updated   = NOW
   │
5. Response: {status="ok", updated_buckets=85}
   (17 Achsen × 6 Levels = 102 Bucket-Updates pro Klick)
```
