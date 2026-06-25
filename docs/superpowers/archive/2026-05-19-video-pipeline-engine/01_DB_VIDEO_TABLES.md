# 01 — DB-Tabellen Video (KORRIGIERT 2026-05-19)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 1 Foundation
> Status: planned · korrigiert 2026-05-19 nach Real-Stand-Recon

## Real-Stand der DB (gepruft 2026-05-19)

| Tabelle | Existiert | Reuse fuer Pipeline |
|---|---|---|
| `video_clips` (Model `VideoClip`) | ja | **wird erweitert** statt neue Tabelle |
| `scenes` (Model `Scene`) | ja, mit `ai_caption` / `ai_mood` / `ai_tags` | **wird erweitert** statt neue Tabelle |
| `audio_video_anchors` | ja | Cross-Modal nutzt diese |

## Bereits vorhandene Spalten (NICHT doppelt anlegen)

`video_clips`:
- `file_path`, `proxy_path`, `duration`, `width`, `height`, `fps`, `codec`, `playback_offset`, `deleted_at`

`scenes`:
- `start_time`, `end_time`, `label`, `energy`, `ai_caption` (JSON), `ai_mood`, `ai_tags`

## Neu hinzuzufuegende Spalten

### `video_clips` (ALTER TABLE)

```sql
ALTER TABLE video_clips ADD COLUMN video_pipeline_status TEXT;
-- "pending" | "running" | "done" | "failed" | "partial"

ALTER TABLE video_clips ADD COLUMN video_pipeline_checkpoint_path TEXT;
-- JSON-Datei fuer Resume

ALTER TABLE video_clips ADD COLUMN stream_sha256 TEXT;
-- content-hash, Container-uebergreifend

ALTER TABLE video_clips ADD COLUMN embeddings_path TEXT;
-- SigLIP-Vision-Embeddings als .npy

ALTER TABLE video_clips ADD COLUMN motion_path TEXT;
-- RAFT-Motion-Aggregate als .json

ALTER TABLE video_clips ADD COLUMN proxy_status TEXT;
-- "pending" | "done" | "failed" | "skipped"
-- (proxy_path existiert schon; status fehlt)
```

### `scenes` (ALTER TABLE)

```sql
ALTER TABLE scenes ADD COLUMN scene_index INTEGER;
-- Reihenfolge innerhalb Video (0-basiert)

ALTER TABLE scenes ADD COLUMN keyframe_paths TEXT;
-- JSON: ["keyframes/0_start.jpg", "keyframes/0_mid.jpg", "keyframes/0_end.jpg"]

ALTER TABLE scenes ADD COLUMN embedding_indices TEXT;
-- JSON: [42, 43, 44] -> Zeilen in video_clips.embeddings_path
```

### Indizes

```sql
CREATE INDEX IF NOT EXISTS ix_video_clips_stream_sha256
    ON video_clips(stream_sha256);
CREATE INDEX IF NOT EXISTS ix_video_clips_pipeline_status
    ON video_clips(video_pipeline_status);
CREATE INDEX IF NOT EXISTS ix_scenes_scene_index
    ON scenes(video_clip_id, scene_index);
```

## Out of Scope

- **Globale `analysis_jobs`-Tabelle** → Plan C (D-046).
- **VideoFrameArtifact** als eigene Tabelle — verworfen. Files-on-Disk + `Scene.keyframe_paths` reichen.

## Migrations-Strategie

Analog migrations.py-Pattern (siehe SCHNITT A1-A3, Audio-V2 stems-Migration):

```python
# database/migrations.py — neue Funktion
def migrate_video_pipeline_columns(engine):
    """Idempotent — fuegt video_clips + scenes Spalten + Indizes hinzu."""
    insp = inspect(get_raw_engine())

    if "video_clips" in insp.get_table_names():
        vc_cols = {c["name"] for c in insp.get_columns("video_clips")}
        with engine.begin() as conn:
            if "video_pipeline_status" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN video_pipeline_status TEXT"))
            if "video_pipeline_checkpoint_path" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN video_pipeline_checkpoint_path TEXT"))
            if "stream_sha256" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN stream_sha256 TEXT"))
            if "embeddings_path" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN embeddings_path TEXT"))
            if "motion_path" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN motion_path TEXT"))
            if "proxy_status" not in vc_cols:
                conn.execute(text(
                    "ALTER TABLE video_clips ADD COLUMN proxy_status TEXT"))

    if "scenes" in insp.get_table_names():
        sc_cols = {c["name"] for c in insp.get_columns("scenes")}
        with engine.begin() as conn:
            if "scene_index" not in sc_cols:
                conn.execute(text(
                    "ALTER TABLE scenes ADD COLUMN scene_index INTEGER"))
            if "keyframe_paths" not in sc_cols:
                conn.execute(text(
                    "ALTER TABLE scenes ADD COLUMN keyframe_paths TEXT"))
            if "embedding_indices" not in sc_cols:
                conn.execute(text(
                    "ALTER TABLE scenes ADD COLUMN embedding_indices TEXT"))

    # Indizes
    insp = inspect(get_raw_engine())
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        if "video_clips" in existing_tables:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_video_clips_stream_sha256 "
                "ON video_clips(stream_sha256)"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_video_clips_pipeline_status "
                "ON video_clips(video_pipeline_status)"))
        if "scenes" in existing_tables:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scenes_scene_index "
                "ON scenes(video_clip_id, scene_index)"))
```

## Model-Klasse-Erweiterung

`database/models.py` — `VideoClip` + `Scene` Klassen bekommen neue Column-Definitionen analog. SQLAlchemy-Layer + Migration arbeiten parallel (siehe Audio-V2 stem_pipeline_status-Vorbild).

## Sub-Task-Reihenfolge (TDD)

- **T1.1** Recon — DONE (2026-05-19 01:30)
- **T1.2** RED — Test: `tests/test_db/test_video_pipeline_migration.py`. Erwartet: Spalten existieren nach Migration. Soll fail.
- **T1.3** GREEN — `database/migrations.py` Funktion + `database/models.py` Column-Erweiterung.
- **T1.4** Verify GREEN — pytest + manuelles `inspect()` auf Test-DB.
- **T1.5** REFACTOR — Falls Duplikation, Refactor.
- **T1.6** Idempotenz-Test — 2× Migration-Lauf, kein Fehler.
- **T1.7** Vault-Log + Commit.

## Verifikation

- `pytest tests/test_db/test_video_pipeline_migration.py -v` gruen
- 2× Migration-Lauf idempotent
- Bestehende Tests gruen (kein Regression)

## Offene Klaerungs-Punkte

- [ ] `proxy_status` ueberhaupt noetig oder reicht "proxy_path is None / not None"?
- [ ] `embedding_indices` als JSON-Liste OK oder besser direkt Numerik-Range (`embedding_start_idx`, `embedding_count`)?

## Commit-Format

```
video-pipe: db schema for pipeline state (phase 01)

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 01 (Tier 1 Foundation)
```
