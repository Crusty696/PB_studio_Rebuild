-- Brain V3 / Plan-Doc 04 Schema 4 — embeddings.db (projekt-spezifisch)
-- Audio + Video Embeddings mit sqlite-vec virtuellen Tabellen fuer KNN.
-- BENOETIGT geladene sqlite-vec Extension (siehe sqlite_init.load_vec_extension).

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

-- CLAP Audio-Embeddings: 512-dim
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
