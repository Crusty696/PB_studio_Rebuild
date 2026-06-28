-- Brain V3 / Phase 1 App-Sync — Media-Hash-Registry
-- Plan-Amendment 2026-05-05 (App-Sync-Block 06_PHASES.md Z.82-96).
--
-- Persistiert sha256-Hashes von Audio/Video-Dateien beim Import,
-- bevor Phase 2 Embeddings berechnet. Schliesst die Phase-1-Luecke
-- "Hash + V3-Schema-Eintrag in V3-DB ablegen" ohne Embedding-Daten
-- zu erfordern.
--
-- Sibling-Tabelle in embedding_cache.db (kein neues DB-File, haelt
-- Plan-Doc 04 "5 SQLite-Files"-Zaehlung ein).

CREATE TABLE IF NOT EXISTS media_hashes (
    media_hash       TEXT PRIMARY KEY,
    media_type       TEXT NOT NULL CHECK(media_type IN ('audio', 'video')),
    source_path      TEXT NOT NULL,
    file_size_bytes  INTEGER NOT NULL,
    computed_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_hashes_type ON media_hashes(media_type);
CREATE INDEX IF NOT EXISTS idx_media_hashes_path ON media_hashes(source_path);
