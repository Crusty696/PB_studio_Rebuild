-- Brain V3 / Plan-Doc 04 Schema 2 — patterns.db (App-global)
-- Audio↔Video Profil-Korrelationen (quantisierte Brücken-Features).

CREATE TABLE IF NOT EXISTS pattern_correlations (
    audio_profile_hash TEXT NOT NULL,
    video_profile_hash TEXT NOT NULL,
    positive_count     INTEGER NOT NULL DEFAULT 0,
    negative_count     INTEGER NOT NULL DEFAULT 0,
    contexts_json      TEXT,
    last_seen          TEXT NOT NULL,
    PRIMARY KEY (audio_profile_hash, video_profile_hash)
);

CREATE INDEX IF NOT EXISTS idx_audio_profile
    ON pattern_correlations(audio_profile_hash);
CREATE INDEX IF NOT EXISTS idx_video_profile
    ON pattern_correlations(video_profile_hash);
