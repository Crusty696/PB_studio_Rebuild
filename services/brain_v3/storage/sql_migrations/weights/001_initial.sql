-- Brain V3 / Plan-Doc 04 Schema 1 — weights.db (App-global)
-- Beta-Bernoulli α/β-Counts pro (Achse, Backoff-Level, Kontext-Key).

CREATE TABLE IF NOT EXISTS axis_weights (
    axis           TEXT NOT NULL,
    context_level  INTEGER NOT NULL CHECK(context_level >= 0 AND context_level <= 5),
    context_key    TEXT NOT NULL,
    positive_count REAL NOT NULL DEFAULT 0,
    negative_count REAL NOT NULL DEFAULT 0,
    last_updated   TEXT NOT NULL,
    PRIMARY KEY (axis, context_level, context_key)
);

CREATE INDEX IF NOT EXISTS idx_axis_level
    ON axis_weights(axis, context_level);
