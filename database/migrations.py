import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import text, inspect

from database.session import engine, get_raw_engine, nullpool_session, APP_ROOT
from database.models import (
    Base, Project, StylePreset,
)

logger = logging.getLogger(__name__)


def _needs_fk_cascade_migration(insp) -> bool:
    """Prüft ob ON DELETE CASCADE in den Child-Tabellen fehlt.

    Bug-16 Fix: Prüft ALLE Child-Tabellen, nicht nur 'scenes'.
    Vorher wurde nur scenes geprüft — beatgrids, waveform_data, timeline_entries
    usw. wurden nie kontrolliert, was zu verwaisten Datensätzen führte.
    """
    # Alle Child-Tabellen die ON DELETE CASCADE benötigen
    child_tables = [
        "scenes", "beatgrids", "waveform_data", "pacing_blueprints",
        "audio_video_anchors", "clip_anchors", "timeline_entries",
        "structure_segments", "hotcues",
    ]
    existing_tables = set(insp.get_table_names())
    try:
        with engine.connect() as conn:
            for tname in child_tables:
                if tname not in existing_tables:
                    continue
                result = conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE name=:tname"),
                    {"tname": tname},
                )
                row = result.fetchone()
                # Wenn sql vorhanden aber kein CASCADE → Migration nötig
                if row and row[0] and "ON DELETE CASCADE" not in row[0].upper():
                    return True
    except Exception:
        return False
    return False


def _migrate_fk_cascade():
    """Recreate alle Tabellen mit ON DELETE CASCADE (SQLite kann FK nicht ALTER).

    SICHERHEIT: Erstellt vorher ein Backup der DB-Datei.
    """
    # Backup vor destruktiver Migration — mit Verifikation
    # Dynamischer Pfad: nutzt die URL der aktuellen Engine
    try:
        raw = get_raw_engine()
        db_path = Path(str(raw.url).replace("sqlite:///", ""))
    except Exception:
        db_path = APP_ROOT / "pb_studio.db"
    backup_path = None
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.backup_before_fk_migration")
        shutil.copy2(db_path, backup_path)
        # Sicherheits-Check: Backup muss existieren und gleiche Groesse haben
        original_size = db_path.stat().st_size
        backup_size = backup_path.stat().st_size if backup_path.exists() else 0
        if not backup_path.exists() or backup_size != original_size:
            raise RuntimeError(
                f"FK-Migration abgebrochen: Backup-Verifikation fehlgeschlagen "
                f"(original={original_size}B, backup={backup_size}B). Daten unveraendert."
            )
        logger.info("FK-CASCADE Migration: Backup verifiziert (%d Bytes): %s", backup_size, backup_path)

    logger.info("FK-CASCADE Migration: Recreating tables with ON DELETE CASCADE...")

    try:
        with engine.begin() as conn:
            # FK temporaer aus, damit wir Tabellen droppen koennen
            conn.execute(text("PRAGMA foreign_keys=OFF"))

            table_names = [
                "clip_anchors", "audio_video_anchors", "scenes",
                "beatgrids", "waveform_data", "pacing_blueprints",
                "timeline_entries", "structure_segments", "hotcues",
                "ai_pacing_memory", "style_presets",
                "audio_tracks", "video_clips",
            ]
            _ALLOWED_TABLES = {
                "audio_tracks", "video_clips", "scenes", "beatgrids",
                "waveform_data", "pacing_blueprints", "audio_video_anchors",
                "clip_anchors", "timeline_entries", "structure_segments",
                "hotcues", "ai_pacing_memory", "style_presets",
            }
            for tname in table_names:
                # F-012 Fix: Echte Validierung statt assert (assert wird durch -O deaktiviert)
                if tname not in _ALLOWED_TABLES:
                    raise ValueError(f"Unerlaubter Tabellenname: {tname}")
                conn.execute(text('DROP TABLE IF EXISTS "' + tname + '"'))

            # FK wieder an
            conn.execute(text("PRAGMA foreign_keys=ON"))

        # Tabellen mit korrektem Schema neu erstellen
        Base.metadata.create_all(engine)
    except Exception:
        logger.error("FK-CASCADE Migration FEHLGESCHLAGEN! Backup liegt unter: %s",
                     backup_path if db_path.exists() else "N/A")
        raise
    logger.info("FK-CASCADE Migration abgeschlossen.")


def init_db():
    """Erstellt alle Tabellen und ein Default-Projekt, falls noch keines existiert."""
    Base.metadata.create_all(engine)

    _raw = get_raw_engine()
    insp = inspect(_raw)

    # Migration: ON DELETE CASCADE nachrüsten (SQLite braucht Table-Rebuild)
    if _needs_fk_cascade_migration(insp):
        _migrate_fk_cascade()

    # Phase 3: Migrate existing beatgrids table (add new columns if missing)
    insp = inspect(get_raw_engine())  # refresh nach möglicher Migration
    if "beatgrids" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("beatgrids")}
        with engine.begin() as conn:
            if "downbeat_positions" not in columns:
                conn.execute(text("ALTER TABLE beatgrids ADD COLUMN downbeat_positions TEXT"))
            if "energy_per_beat" not in columns:
                conn.execute(text("ALTER TABLE beatgrids ADD COLUMN energy_per_beat TEXT"))

    # Migration: source_start / source_end in timeline_entries nachrüsten
    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "source_start" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_start FLOAT DEFAULT 0.0"))
            if "source_end" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_end FLOAT"))

    # Bug-13 Fix: crossfade_duration / brightness / contrast in timeline_entries nachrüsten
    # Diese Spalten existieren im ORM-Modell aber fehlten in den ALTER TABLE Migrationen.
    # Ohne diesen Block crasht _apply_effects() / _on_effects_clip_changed() auf bestehenden DBs
    # mit: OperationalError: no such column: timeline_entries.crossfade_duration
    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "crossfade_duration" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN crossfade_duration FLOAT DEFAULT 0.0"))
            if "brightness" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN brightness FLOAT DEFAULT 0.0"))
            if "contrast" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN contrast FLOAT DEFAULT 1.0"))

    # Migration: ai_pacing_memory Tabelle nachrüsten (neue Spalten falls Tabelle alt)
    insp = inspect(get_raw_engine())
    if "ai_pacing_memory" in insp.get_table_names():
        ai_cols = {c["name"] for c in insp.get_columns("ai_pacing_memory")}
        with engine.begin() as conn:
            import re as _re
            _VALID_COL = _re.compile(r"^[a-z_]+$")
            _VALID_TYPE = _re.compile(r"^[A-Z]+$")
            for col_name, col_type in [
                ("bass_energy", "FLOAT"), ("drum_energy", "FLOAT"),
                ("siglip_tags", "TEXT"), ("section_type", "TEXT"),
                ("audio_track_id", "INTEGER"), ("scene_id", "INTEGER"),
            ]:
                # F-012 Fix: Echte Validierung statt assert (assert wird durch -O deaktiviert)
                if not _VALID_COL.match(col_name):
                    raise ValueError(f"Ungueltiger Spaltenname: {col_name}")
                if not _VALID_TYPE.match(col_type):
                    raise ValueError(f"Ungueltiger Spaltentyp: {col_type}")
                if col_name not in ai_cols:
                    conn.execute(text(
                        'ALTER TABLE ai_pacing_memory ADD COLUMN "' + col_name + '" ' + col_type
                    ))

    # K2 Fix: stem_*_path Spalten in audio_tracks nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_columns = {c["name"] for c in insp.get_columns("audio_tracks")}
        with engine.begin() as conn:
            for stem_col in ["stem_vocals_path", "stem_drums_path", "stem_bass_path", "stem_other_path"]:
                if stem_col not in at_columns:
                    import re as _re2
                    if not _re2.match(r"^[a-z_]+$", stem_col):
                        logger.warning("Ungültiger Spaltenname übersprungen: %s", stem_col)
                        continue
                    conn.execute(text(f"ALTER TABLE audio_tracks ADD COLUMN {stem_col} TEXT"))

    # Phase 4: Erweiterte Audio-Analyse Spalten nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_columns = {c["name"] for c in insp.get_columns("audio_tracks")}
        import re as _re4
        _VALID_COL4 = _re4.compile(r"^[a-z_]+$")
        _VALID_TYPE4 = _re4.compile(r"^[A-Z]+$")
        with engine.begin() as conn:
            for col_name, col_type, col_default in [
                ("key_confidence", "FLOAT", None),
                ("lufs", "FLOAT", None),
                ("mood", "TEXT", None),
                ("genre", "TEXT", None),
                ("is_dj_mix", "BOOLEAN", "0"),
                ("spectral_bands", "TEXT", None),
            ]:
                if not _VALID_COL4.match(col_name):
                    raise ValueError(f"Ungueltiger Spaltenname: {col_name}")
                if not _VALID_TYPE4.match(col_type):
                    raise ValueError(f"Ungueltiger Spaltentyp: {col_type}")
                if col_name not in at_columns:
                    stmt = f"ALTER TABLE audio_tracks ADD COLUMN {col_name} {col_type}"
                    if col_default is not None:
                        # P2-06: SQL-Injection Schutz fuer col_default
                        if not re.match(r"^[a-zA-Z0-9_.'\"-]+$", str(col_default)):
                            logger.warning("Skipping unsafe col_default: %s", col_default)
                            continue
                        stmt += f" DEFAULT {col_default}"
                    conn.execute(text(stmt))

    # Phase 4: Indizes auf neue Tabellen
    insp = inspect(get_raw_engine())
    with engine.begin() as conn:
        if "structure_segments" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_structure_segments_audio_track_id ON structure_segments(audio_track_id)"))
        if "hotcues" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hotcues_audio_track_id ON hotcues(audio_track_id)"))

    # Phase 4: Default Style-Presets einfügen (NullPool: init_db laeuft beim Start)
    with nullpool_session() as session:
        if "style_presets" in insp.get_table_names() and not session.query(StylePreset).first():
            defaults = [
                StylePreset(name="Standard", cut_rate=1.0, energy_reactivity=0.7, breakdown_behavior="halve", description="Ausgewogener Mix"),
                StylePreset(name="Techno", cut_rate=1.2, energy_reactivity=0.9, breakdown_behavior="halve", beat_weight=1.5, kick_weight=1.5, description="Kick-betont, schnelle Cuts"),
                StylePreset(name="House", cut_rate=0.8, energy_reactivity=0.6, breakdown_behavior="halve", description="Groovy, mittleres Tempo"),
                StylePreset(name="Drum & Bass", cut_rate=1.5, energy_reactivity=0.95, breakdown_behavior="16beat", beat_weight=1.2, snare_weight=1.5, description="Schnell, Snare-fokussiert"),
                StylePreset(name="Hip-Hop", cut_rate=0.6, energy_reactivity=0.5, breakdown_behavior="none", description="Laid-back, langsame Cuts"),
                StylePreset(name="Ambient", cut_rate=0.3, energy_reactivity=0.2, breakdown_behavior="none", min_clip_duration=4.0, max_clip_duration=15.0, description="Atmosphärisch, lange Clips"),
                StylePreset(name="Minimal", cut_rate=0.7, energy_reactivity=0.4, breakdown_behavior="halve", description="Reduziert, subtile Wechsel"),
                StylePreset(name="Cinematic", cut_rate=0.5, energy_reactivity=0.6, breakdown_behavior="none", min_clip_duration=3.0, max_clip_duration=12.0, description="Filmisch, dramatische Übergänge"),
                StylePreset(name="Festival", cut_rate=1.8, energy_reactivity=1.0, breakdown_behavior="16beat", beat_weight=1.5, kick_weight=1.5, snare_weight=1.2, description="Maximum Energy, schnellste Cuts"),
            ]
            session.add_all(defaults)
            # B-003 Fix: Fehlerbehandlung für session.commit() hinzufügen
            try:
                session.commit()
            except Exception as e:
                logger.error("Fehler beim Einfügen von Style-Presets: %s", e)
                # Rollback automatisch beim Kontext-Exit

    # H5 Fix: Indizes auf Foreign-Key-Spalten erstellen (SQLite macht das nicht automatisch)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_tracks_project_id ON audio_tracks(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_video_clips_project_id ON video_clips(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scenes_video_clip_id ON scenes(video_clip_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waveform_data_audio_track_id ON waveform_data(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_timeline_entries_project_id ON timeline_entries(project_id)"))
        # DB-23/24 Fix: Fehlende Indizes auf audio_video_anchors + clip_anchors
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_audio_track_id ON audio_video_anchors(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_video_clip_id ON audio_video_anchors(video_clip_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_clip_anchors_timeline_entry_id ON clip_anchors(timeline_entry_id)"))
        # P2-02: UNIQUE Index auf beatgrids.audio_track_id (verhindert Duplikate)
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
        # Index auf ai_pacing_memory.audio_track_id (Abfrage-Performance bei vielen gelernten Regeln)
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_pacing_memory_audio_track_id ON ai_pacing_memory(audio_track_id)"))

    # AUD-11: model_registry Index
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_source ON model_registry(source)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_last_used ON model_registry(last_used_at)"))

    # AUD-12: agent_feedback Index (AP-5 — Auto-Prompt-Optimization)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_rating ON agent_feedback(rating)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_action ON agent_feedback(action_name)"))

    with nullpool_session() as session:
        if not session.query(Project).first():
            session.add(Project(name="Default", path=".", resolution="1920x1080", fps=30.0))
            # B-003 Fix: Fehlerbehandlung für session.commit() hinzufügen
            try:
                session.commit()
            except Exception as e:
                logger.error("Fehler beim Einfügen des Standard-Projekts: %s", e)
                # Rollback automatisch beim Kontext-Exit
