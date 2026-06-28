-- B-372: Ein Medien-Hash kann mehrere Embedding-Varianten haben.
-- Die alte Tabelle nutzte media_hash als alleinigen Primary Key und
-- ueberschrieb dadurch andere model_name/model_version-Varianten.

CREATE TABLE media_embedding_index_new (
    media_hash TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK(media_type IN ('audio', 'video')),
    embedding_path TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    file_size_bytes INTEGER,
    PRIMARY KEY (media_hash, model_name, model_version)
);

INSERT OR REPLACE INTO media_embedding_index_new (
    media_hash,
    media_type,
    embedding_path,
    model_name,
    model_version,
    computed_at,
    file_size_bytes
)
SELECT
    media_hash,
    media_type,
    embedding_path,
    model_name,
    model_version,
    computed_at,
    file_size_bytes
FROM media_embedding_index;

DROP TABLE media_embedding_index;
ALTER TABLE media_embedding_index_new RENAME TO media_embedding_index;

CREATE INDEX IF NOT EXISTS idx_media_embedding_model
    ON media_embedding_index(model_name, model_version);
