-- Brain V3 / Plan-Doc 04 Schema 3 — embedding_cache.db
-- App-globaler Hash-basierter Embedding-Cache.
-- Embedding-Files liegen physisch in %APPDATA%\PB_Studio\brain_v3\embeddings\,
-- diese Tabelle ist nur Index.

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
