import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import text, inspect
from sqlalchemy.schema import CreateTable

from database import session as _session  # B-189: lazy APP_ROOT-Lookup nach set_project()
from database.session import engine, get_raw_engine, nullpool_session
from database.models import (
    Base, StylePreset,
)


def _app_root() -> Path:
    """B-189: Liest ``database.session.APP_ROOT`` zur Laufzeit, sodass
    Aufrufer nach ``set_project()`` den aktuellen Projekt-Pfad sehen.
    Ein direktes ``from database.session import APP_ROOT`` faengt
    nur den Wert zum Modul-Load-Zeitpunkt ein.
    """
    return _session.APP_ROOT


# B-189: ``alembic.ini`` und das ``database/alembic/``-Verzeichnis
# sind Repo-Assets, NICHT Projekt-Assets — sie wandern nicht mit
# ``set_project()``. Daher hier ein statischer Pfad relativ zur
# ``migrations.py`` (Repo-Wurzel = parent-of-database/), unabhaengig
# vom Lauzeit-APP_ROOT.
_REPO_ROOT = Path(__file__).resolve().parent.parent
from services.errors import MigrationError

logger = logging.getLogger(__name__)

# Alembic baseline revision — must match the revision in the initial migration file.
# M-41 Fix: Updated to match actual initial migration revision
_ALEMBIC_BASELINE_REV = "beb242bcd1fb"


def _get_create_table_ddl(sa_table, eng) -> str:
    """Render the CREATE TABLE DDL for a SQLAlchemy Table object.

    Uses the engine's dialect so the output is valid SQLite SQL.
    """
    return str(CreateTable(sa_table).compile(eng)).strip()


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
    except Exception:  # broad catch intentional — DB inspection can fail in many ways
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
    except (AttributeError, ValueError):
        db_path = _app_root() / "pb_studio.db"
    backup_path = None
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.backup_before_fk_migration")
        shutil.copy2(db_path, backup_path)

        # M-6 Fix: Enhanced backup verification
        # 1. Check: Backup must exist and have same size
        original_size = db_path.stat().st_size
        backup_size = backup_path.stat().st_size if backup_path.exists() else 0
        if not backup_path.exists() or backup_size != original_size:
            raise MigrationError(
                f"FK-Migration abgebrochen: Backup-Verifikation fehlgeschlagen "
                f"(original={original_size}B, backup={backup_size}B). Daten unveraendert."
            )

        # 2. Check: Backup must be a valid, readable SQLite database
        import sqlite3
        try:
            with sqlite3.connect(str(backup_path), timeout=5.0) as backup_conn:
                cursor = backup_conn.cursor()
                # Verify we can read the schema (ensures DB is not corrupted)
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                cursor.fetchone()
        except (sqlite3.Error, OSError) as e:
            # If backup is unreadable, remove it and fail the migration
            if backup_path.exists():
                backup_path.unlink()
            raise MigrationError(
                f"FK-Migration abgebrochen: Backup ist nicht lesbar oder korrupt ({e}). "
                f"Daten unveraendert."
            ) from e

        logger.info("FK-CASCADE Migration: Backup verifiziert (%d Bytes): %s", backup_size, backup_path)

    logger.info("FK-CASCADE Migration: Recreating tables with ON DELETE CASCADE (rename-and-copy)...")

    # Tables that need FK CASCADE rebuild, ordered children-first to respect FK deps.
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
            raise MigrationError(f"Unerlaubter Tabellenname: {tname}", table=tname)
        # MEDIUM-6 FIX: Defense-in-depth regex validator against SQL injection
        if not re.match(r'^[a-z_]+$', tname):
            raise ValueError(f"Invalid table name: {tname}")

    try:
        # SQLite PRAGMA foreign_keys MUST be set OUTSIDE a transaction.
        # Use a raw DBAPI connection to avoid SQLAlchemy's auto-transaction
        # and bypass the connect-event listener that sets foreign_keys=ON.
        raw_engine = get_raw_engine()
        raw_conn = raw_engine.raw_connection()
        try:
            raw_conn.isolation_level = None  # autocommit mode — PRAGMAs work here
            cursor = raw_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")

            # Verify PRAGMA actually took effect
            cursor.execute("PRAGMA foreign_keys")
            fk_status = cursor.fetchone()
            if fk_status and fk_status[0] != 0:
                raise MigrationError(
                    "PRAGMA foreign_keys=OFF konnte nicht gesetzt werden. "
                    "Migration abgebrochen um Datenverlust zu vermeiden."
                )

            # Determine which tables actually exist in the DB
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            # Use the SQLite "rename-and-copy" pattern for each table:
            # 1. ALTER TABLE x RENAME TO x_old_fk_backup
            # 2. CREATE TABLE x (with correct FK CASCADE from SQLAlchemy metadata)
            # 3. INSERT INTO x SELECT matching_columns FROM x_old_fk_backup
            # 4. DROP TABLE x_old_fk_backup
            # This preserves ALL data.
            cursor.execute("BEGIN")
            try:
                for tname in table_names:
                    if tname not in existing_tables:
                        continue
                    backup_tname = f"{tname}_old_fk_backup"

                    # Step 1: Rename the old table
                    cursor.execute(f'ALTER TABLE "{tname}" RENAME TO "{backup_tname}"')

                    # Step 2: Create the new table with correct schema from models
                    sa_table = Base.metadata.tables.get(tname)
                    if sa_table is None:
                        # Table not in models — rename back and skip
                        cursor.execute(f'ALTER TABLE "{backup_tname}" RENAME TO "{tname}"')
                        logger.warning("FK-Migration: Tabelle '%s' nicht in Modellen — uebersprungen", tname)
                        continue

                    create_ddl = _get_create_table_ddl(sa_table, raw_engine)
                    cursor.execute(create_ddl)

                    # Step 3: Copy data — use column intersection (old table may have
                    # fewer columns than new schema, or columns may have been removed)
                    cursor.execute(f'PRAGMA table_info("{backup_tname}")')
                    old_columns = {row[1] for row in cursor.fetchall()}
                    cursor.execute(f'PRAGMA table_info("{tname}")')
                    new_columns = {row[1] for row in cursor.fetchall()}
                    common_columns = sorted(old_columns & new_columns)

                    if common_columns:
                        cols_str = ", ".join(f'"{c}"' for c in common_columns)
                        # B-037 / B608: tname + cols_str stammen aus
                        # PRAGMA-table_info-Inspektion (DB-Schema) — kein
                        # User-Input. SQL-Injection-Vektor existiert nicht.
                        cursor.execute(
                            f'INSERT INTO "{tname}" ({cols_str}) SELECT {cols_str} FROM "{backup_tname}"'  # nosec B608
                        )
                        copied_rows = cursor.rowcount
                        logger.info("FK-Migration: %s — %d Zeilen kopiert (%d Spalten)",
                                    tname, copied_rows, len(common_columns))
                    else:
                        logger.warning("FK-Migration: %s — keine gemeinsamen Spalten, Tabelle leer", tname)

                    # Step 4: Drop the old backup table
                    cursor.execute(f'DROP TABLE "{backup_tname}"')

                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                # After rollback, check if any _old_fk_backup tables remain
                # and rename them back to recover
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_old_fk_backup'")
                orphaned = [row[0] for row in cursor.fetchall()]
                for orphan in orphaned:
                    original = orphan.replace("_old_fk_backup", "")
                    try:
                        # Drop the partially-created new table if it exists
                        cursor.execute(f'DROP TABLE IF EXISTS "{original}"')
                        cursor.execute(f'ALTER TABLE "{orphan}" RENAME TO "{original}"')
                        logger.info("FK-Migration Rollback: '%s' -> '%s' wiederhergestellt", orphan, original)
                    except Exception as rename_err:
                        logger.error("FK-Migration Rollback fehlgeschlagen fuer '%s': %s", orphan, rename_err)
                raise
        finally:
            # B-174: PRAGMA foreign_keys=ON IMMER wieder einschalten,
            # auch im Fehler-Pfad. Sonst behaelt die gepoolte Connection
            # FK=OFF und naechste Service-Anfragen umgehen FK-Constraints
            # silent — DELETE auf Project loescht keine Child-Tabellen mehr.
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception as fk_err:
                logger.error("PRAGMA foreign_keys=ON failed: %s", fk_err)
            try:
                cursor.close()
            except Exception:
                pass
            raw_conn.close()

        # Create any tables that are in metadata but did not exist yet
        Base.metadata.create_all(engine)

    except MigrationError:
        logger.error("FK-CASCADE Migration FEHLGESCHLAGEN! Backup liegt unter: %s",
                     backup_path if db_path.exists() else "N/A")
        raise
    except Exception:
        logger.error("FK-CASCADE Migration FEHLGESCHLAGEN! Backup liegt unter: %s",
                     backup_path if db_path.exists() else "N/A")
        # Attempt automatic restore from backup
        if backup_path and backup_path.exists():
            try:
                engine.dispose()
                shutil.copy2(backup_path, db_path)
                logger.info("Backup automatisch wiederhergestellt von: %s", backup_path)
            except Exception as restore_error:
                logger.critical("Backup-Wiederherstellung FEHLGESCHLAGEN: %s — Manuell wiederherstellen von: %s",
                                restore_error, backup_path)
        raise
    logger.info("FK-CASCADE Migration abgeschlossen — alle Daten erhalten.")
    # B-191: Backup nach erfolgreicher Migration aufraeumen, sonst Disk-Leak.
    # Bei mehrmaligem Aufruf ueberschriebe ``shutil.copy2`` zwar denselben
    # Pfad — aber die Datei blieb im Erfolgsfall fuer immer liegen.
    _cleanup_fk_migration_backup(backup_path)


def _cleanup_fk_migration_backup(backup_path):
    """B-191: Loescht das FK-Migrations-Backup nach erfolgreicher Migration.

    Wird ausschliesslich am Ende des Erfolgspfads von
    ``_migrate_fk_cascade()`` aufgerufen. Auf None oder fehlende Datei
    no-op (idempotent). Im Fehlerfall der Migration bleibt der Backup
    bewusst stehen, weil der Exception-Pfad ihn fuer Auto-Restore nutzt.

    Wer ein laengeres Recovery-Fenster will, kann vor Migration einen
    eigenen Cloud-/Git-Backup ziehen — die FK-Migration ist seit B-174
    gut getestet, sodass ein lokales Sicherheitsnetz nach Erfolg nur
    Disk verbraucht.
    """
    if backup_path is None:
        return
    try:
        if backup_path.exists():
            size = backup_path.stat().st_size
            backup_path.unlink()
            logger.info(
                "FK-Migration: Backup nach Erfolg geloescht (%d Bytes): %s",
                size, backup_path,
            )
    except OSError as exc:
        # Disk-Cleanup darf den App-Start nicht killen.
        logger.warning(
            "FK-Migration: Backup-Cleanup fehlgeschlagen (%s) — Datei %s "
            "bleibt liegen, manuelles Aufraeumen empfohlen.",
            exc, backup_path,
        )


def _run_alembic_migrations():
    """Run Alembic migrations to bring the database to the latest schema version.

    Handles three scenarios:
    1. Fresh DB (no tables) → run upgrade("head") to create everything
    2. Legacy DB (tables exist, no alembic_version) → stamp baseline, then upgrade
    3. Alembic-managed DB → run upgrade("head") for any pending migrations
    """
    from alembic.config import Config
    from alembic import command

    _raw = get_raw_engine()
    insp = inspect(_raw)
    existing_tables = set(insp.get_table_names())

    # B-189: Alembic-Assets liegen im Repo, nicht im wechselbaren
    # Projekt-APP_ROOT. ``_REPO_ROOT`` ist statisch.
    alembic_cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(_REPO_ROOT / "database" / "alembic")
    )
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    if "alembic_version" not in existing_tables and "projects" in existing_tables:
        # Legacy DB: tables exist but Alembic was never used.
        # Stamp the baseline revision so Alembic knows the schema is current.
        logger.info("Legacy-DB erkannt — stampe Alembic Baseline (%s)", _ALEMBIC_BASELINE_REV)
        command.stamp(alembic_cfg, _ALEMBIC_BASELINE_REV)

    # B-498: Snapshot der Haupt-DB BEVOR Alembic Schema-Aenderungen anwendet
    # (nur wenn tatsaechlich Revisionen anstehen). Das bestehende
    # FK-Migrations-Backup (B-174/B-191) bleibt davon unberuehrt.
    _backup_before_alembic_upgrade(alembic_cfg)

    # Run any pending migrations (creates tables on fresh DBs, applies deltas on existing)
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic-Migrationen abgeschlossen (head).")


def _backup_before_alembic_upgrade(alembic_cfg) -> None:
    """B-498: Pre-Migration-Backup vor ``alembic upgrade head``.

    Backup wird NUR gezogen wenn (a) die DB Bestandsdaten haben kann
    (``projects``- und ``alembic_version``-Tabelle existieren) und (b)
    tatsaechlich Revisionen anstehen (current revision != head) — sonst
    wuerde jeder App-Start ein neues Backup erzeugen. Fehler in diesem
    Pfad werden geloggt und blockieren die Migration nicht
    (``run_pre_migration_backup`` faengt intern, der Revision-Check hier
    ist zusaetzlich defensiv gekapselt).
    """
    try:
        from alembic.script import ScriptDirectory

        _raw = get_raw_engine()
        insp = inspect(_raw)
        tables = set(insp.get_table_names())
        if "projects" not in tables or "alembic_version" not in tables:
            # Frische DB ohne Bestandsdaten — nichts Sicherungswuerdiges.
            return

        with _raw.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        heads = set(ScriptDirectory.from_config(alembic_cfg).get_heads())
        if current in heads:
            return  # bereits auf head — kein Schema-Change, kein Backup noetig

        from services.backup_service import run_pre_migration_backup

        db_path = Path(_raw.url.database)
        backup_path = run_pre_migration_backup(
            db_path=db_path,
            backup_dir=db_path.parent / "storage" / "backups",
        )
        if backup_path is not None:
            logger.info(
                "B-498: Pre-Migration-Backup erstellt (current=%s, heads=%s): %s",
                current, heads, backup_path,
            )
    except Exception as exc:
        logger.error(
            "B-498: Pre-Migration-Backup uebersprungen (Fehler) — Migration "
            "laeuft trotzdem weiter: %s",
            exc, exc_info=True,
        )


def _run_legacy_migrations():
    """Run legacy hand-written migrations for pre-Alembic schema updates.

    These are idempotent ALTER TABLE / CREATE INDEX statements that bring
    old databases up to the baseline schema. They are safe to run even on
    databases that are already at the baseline — every statement checks
    for column/index existence before acting.

    FROZEN (B-509 / CRF-011, 2026-06-12): Diese Funktion ist eingefroren —
    neue Schemaaenderungen werden NUR noch als Alembic-Revisionen unter
    ``database/alembic/versions/`` angelegt, NICHT mehr hier. Die
    bestehenden Bloecke bleiben fuer Bestands-DBs erhalten (nicht
    loeschen!). Die post-Baseline-Teile (locked, timeline_snapshots,
    project_notes, video_pipeline-Spalten) sind zusaetzlich idempotent in
    Alembic-Revision ``d4e5f6a7b8c9_post_baseline_consolidation``
    konsolidiert.
    """
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

    # AUD-83: Onset Rhythm Intelligence + AUDIT-FIXPLAN-2026-07-07 / A3: beatgrids.stem_weighted_energy nachrüsten
    insp = inspect(get_raw_engine())
    if "beatgrids" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("beatgrids")}
        with engine.begin() as conn:
            for col_name, col_type in [
                ("onset_kick_data", "TEXT"),
                ("onset_snare_data", "TEXT"),
                ("onset_hihat_data", "TEXT"),
                ("syncopation_score", "FLOAT"),
                ("groove_template", "TEXT"),
                ("stem_weighted_energy", "TEXT"),
            ]:
                if col_name not in columns:
                    conn.execute(
                        text(f"ALTER TABLE beatgrids ADD COLUMN {col_name} {col_type}")
                    )

    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "source_start" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_start FLOAT DEFAULT 0.0"))
            if "source_end" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_end FLOAT"))

    # Bug-13 Fix: crossfade_duration / brightness / contrast in timeline_entries nachrüsten
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

    # FROZEN (B-509): neue Schemaaenderungen nur noch via Alembic.
    # Block konsolidiert in Revision d4e5f6a7b8c9_post_baseline_consolidation.
    # SCHNITT-Redesign 2026-05-09: locked-Flag fuer Clip-Locking
    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "locked" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0"))

    # FROZEN (B-509): neue Schemaaenderungen nur noch via Alembic.
    # Block konsolidiert in Revision d4e5f6a7b8c9_post_baseline_consolidation.
    # SCHNITT-Redesign 2026-05-09: Tabelle fuer persistente Timeline-Snapshots
    insp = inspect(get_raw_engine())
    if "timeline_snapshots" not in insp.get_table_names():
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE timeline_snapshots ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                "version INTEGER NOT NULL, "
                "label TEXT, "
                "payload_json TEXT NOT NULL, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snapshot_project_version "
            "ON timeline_snapshots(project_id, version)"
        ))

    # FROZEN (B-509): neue Schemaaenderungen nur noch via Alembic.
    # Block konsolidiert in Revision d4e5f6a7b8c9_post_baseline_consolidation.
    # SCHNITT-Redesign 2026-05-09 Task 1.3: project_notes (1:1 pro Projekt)
    insp = inspect(get_raw_engine())
    if "project_notes" not in insp.get_table_names():
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE project_notes ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "project_id INTEGER NOT NULL UNIQUE "
                "REFERENCES projects(id) ON DELETE CASCADE, "
                "content_md TEXT NOT NULL DEFAULT '', "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

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
                if not _VALID_COL.match(col_name):
                    raise MigrationError(f"Ungueltiger Spaltenname: {col_name}", column=col_name)
                if not _VALID_TYPE.match(col_type):
                    raise MigrationError(f"Ungueltiger Spaltentyp: {col_type}", column=col_name)
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
                    raise MigrationError(f"Ungueltiger Spaltenname: {col_name}", column=col_name)
                if not _VALID_TYPE4.match(col_type):
                    raise MigrationError(f"Ungueltiger Spaltentyp: {col_type}", column=col_name)
                if col_name not in at_columns:
                    stmt = f"ALTER TABLE audio_tracks ADD COLUMN {col_name} {col_type}"
                    if col_default is not None:
                        if not re.match(r"^[a-zA-Z0-9_.'\"-]+$", str(col_default)):
                            logger.warning("Skipping unsafe col_default: %s", col_default)
                            continue
                        stmt += f" DEFAULT {col_default}"
                    conn.execute(text(stmt))

    # K3 Fix: transcription Spalte in audio_tracks nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_columns = {c["name"] for c in insp.get_columns("audio_tracks")}
        with engine.begin() as conn:
            if "transcription" not in at_columns:
                conn.execute(text("ALTER TABLE audio_tracks ADD COLUMN transcription TEXT"))

    # F-001 Fix: playback_offset in video_clips nachrüsten
    insp = inspect(get_raw_engine())
    if "video_clips" in insp.get_table_names():
        vc_columns = {c["name"] for c in insp.get_columns("video_clips")}
        with engine.begin() as conn:
            if "playback_offset" not in vc_columns:
                conn.execute(text("ALTER TABLE video_clips ADD COLUMN playback_offset FLOAT DEFAULT 0.0"))

    # Phase 4: Indizes auf neue Tabellen
    insp = inspect(get_raw_engine())
    with engine.begin() as conn:
        if "structure_segments" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_structure_segments_audio_track_id ON structure_segments(audio_track_id)"))
        if "hotcues" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hotcues_audio_track_id ON hotcues(audio_track_id)"))

    # H5 Fix: Indizes auf Foreign-Key-Spalten erstellen (M-40 Fix: mit Tabellen-Existenz-Checks)
    insp = inspect(get_raw_engine())
    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "audio_tracks" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_tracks_project_id ON audio_tracks(project_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tracks_project_file ON audio_tracks(project_id, file_path)"))
        if "video_clips" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_video_clips_project_id ON video_clips(project_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_video_clips_project_file ON video_clips(project_id, file_path)"))
        if "scenes" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scenes_video_clip_id ON scenes(video_clip_id)"))
        if "beatgrids" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
        if "waveform_data" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waveform_data_audio_track_id ON waveform_data(audio_track_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_waveform_data_audio_track_id ON waveform_data(audio_track_id)"))
        if "timeline_entries" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_timeline_entries_project_id ON timeline_entries(project_id)"))
        if "audio_video_anchors" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_audio_track_id ON audio_video_anchors(audio_track_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_video_clip_id ON audio_video_anchors(video_clip_id)"))
        if "clip_anchors" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_clip_anchors_timeline_entry_id ON clip_anchors(timeline_entry_id)"))
        if "ai_pacing_memory" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_pacing_memory_audio_track_id ON ai_pacing_memory(audio_track_id)"))

    # AUD-11: model_registry Index (M-40 Fix: mit Tabellen-Existenz-Check)
    if "model_registry" in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_source ON model_registry(source)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_last_used ON model_registry(last_used_at)"))

    # AUD-12: agent_feedback Index (M-40 Fix: mit Tabellen-Existenz-Check)
    if "agent_feedback" in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_rating ON agent_feedback(rating)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_action ON agent_feedback(action_name)"))

    # AUD-84: ML Key Detection — Modulation + Tension Spalten nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_cols = {c["name"] for c in insp.get_columns("audio_tracks")}
        with engine.begin() as conn:
            if "key_modulation_data" not in at_cols:
                conn.execute(text("ALTER TABLE audio_tracks ADD COLUMN key_modulation_data TEXT"))
            if "harmonic_tension_curve" not in at_cols:
                conn.execute(text("ALTER TABLE audio_tracks ADD COLUMN harmonic_tension_curve TEXT"))

    # AUD-128: Gemma 4 Vision captioning — neue Spalten in scenes nachrüsten
    insp = inspect(get_raw_engine())
    if "scenes" in insp.get_table_names():
        scene_cols = {c["name"] for c in insp.get_columns("scenes")}
        with engine.begin() as conn:
            for col_name, col_type in [
                ("ai_caption", "TEXT"),
                ("ai_mood", "TEXT"),
                ("ai_tags", "TEXT"),
            ]:
                if col_name not in scene_cols:
                    conn.execute(text(f"ALTER TABLE scenes ADD COLUMN {col_name} {col_type}"))

    # FROZEN (B-509): neue Schemaaenderungen nur noch via Alembic.
    # Block konsolidiert in Revision d4e5f6a7b8c9_post_baseline_consolidation.
    # VIDEO-PIPELINE-ENGINE-2026-05-19 Phase 01: Pipeline-State + Cross-Modal-Felder
    # auf video_clips + scenes nachruesten (idempotent).
    insp = inspect(get_raw_engine())
    if "video_clips" in insp.get_table_names():
        vc_cols = {c["name"] for c in insp.get_columns("video_clips")}
        with engine.begin() as conn:
            for col_name, col_type in [
                ("video_pipeline_status", "TEXT"),
                ("video_pipeline_checkpoint_path", "TEXT"),
                ("stream_sha256", "TEXT"),
                ("embeddings_path", "TEXT"),
                ("motion_path", "TEXT"),
                ("proxy_status", "TEXT"),
            ]:
                if col_name not in vc_cols:
                    conn.execute(text(
                        f"ALTER TABLE video_clips ADD COLUMN {col_name} {col_type}"
                    ))

    if "scenes" in insp.get_table_names():
        scene_cols = {c["name"] for c in insp.get_columns("scenes")}
        with engine.begin() as conn:
            for col_name, col_type in [
                ("scene_index", "INTEGER"),
                ("keyframe_paths", "TEXT"),
                ("embedding_indices", "TEXT"),
            ]:
                if col_name not in scene_cols:
                    conn.execute(text(
                        f"ALTER TABLE scenes ADD COLUMN {col_name} {col_type}"
                    ))

    # FROZEN (B-509): neue Schemaaenderungen nur noch via Alembic.
    # Block konsolidiert in Revision d4e5f6a7b8c9_post_baseline_consolidation.
    # VIDEO-PIPELINE-ENGINE-2026-05-19 Phase 01: Indizes auf neue Felder.
    insp = inspect(get_raw_engine())
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        if "video_clips" in existing_tables:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_video_clips_stream_sha256 "
                "ON video_clips(stream_sha256)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_video_clips_pipeline_status "
                "ON video_clips(video_pipeline_status)"
            ))
        if "scenes" in existing_tables:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scenes_scene_index "
                "ON scenes(video_clip_id, scene_index)"
            ))


def _seed_defaults():
    """Seed *immutable* defaults that the App relies on for first-run UX.

    B-190: Frueher legte diese Funktion zusaetzlich ein
    ``Project(name="Default", path=".")``-Stub-Projekt an, das
    ``services/project_manager.py`` beim naechsten ``create_project()``
    wieder hart loeschte. Diese versteckte Kopplung produzierte:
    - relative ``path="."``-Mued-Datensaetze in frischen DBs
    - Tests, die dem Auto-Seed nicht trauten und ihr eigenes Default-
      Projekt anlegten (siehe
      ``tests/test_services/test_ingest_service.py``)
    - Code-Smell in ``project_manager.create_project()`` (musste alle
      Projekte loeschen, bevor er das User-Projekt anlegte).

    Style-Presets bleiben als Bootstrap-Daten erhalten, weil sie
    immutable sind und vom Pacing-Workflow bei jedem Start erwartet
    werden. Konsumenten muessen ``database.session.get_active_project_id()``
    weiter None-tolerant lesen — das war bereits durch H9-FIX
    dokumentiert.
    """
    insp = inspect(get_raw_engine())

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
            # M7-FIX: Kein expliziter commit() — __exit__ macht auto-commit

    # B-190: Kein Auto-Default-Project mehr. Erste Projekt-Anlage erfolgt
    # ueber ``services/project_manager.create_project()``; bis dahin liefert
    # ``get_active_project_id()`` korrekt ``None`` (H9-FIX) und Caller
    # fallen auf den Empty-State zurueck.


def init_db():
    """Initialise the database schema and seed defaults.

    B-091 Fix: Klare Migrations-Strategie ohne Alembic/create_all-Kollision.

    - Fresh-DB (keine Tabellen): create_all() fuer Modell-Tabellen,
      Alembic stamp baseline, dann upgrade head. Nicht alle Head-Tabellen
      leben in database.models (z. B. struct_* / mem_*).
    - Existing-DB ohne alembic_version: legacy als Bring-up auf Baseline,
      dann stamp baseline, dann Alembic upgrade head.
    - Existing-DB mit alembic_version: nur Alembic upgrade head.
    """
    from sqlalchemy import inspect
    from alembic import command

    # B-215 fix: get_raw_engine() umgeht den EngineProxy — ``inspect()`` von
    # SQLAlchemy braucht den echten Engine (NoInspectionAvailable sonst).
    # Alle anderen inspect()-Calls in dieser Datei verwenden bereits
    # get_raw_engine() — diese Stelle war der einzige verbliebene Drift.
    raw_engine = get_raw_engine()
    insp = inspect(raw_engine)
    existing_tables = set(insp.get_table_names())
    is_fresh = len(existing_tables) == 0
    has_alembic_table = "alembic_version" in existing_tables

    alembic_cfg = _alembic_config()

    if is_fresh:
        # Fresh-DB: alle Tabellen aus den Models, dann auf die erste Alembic-
        # Revision stempeln und danach die Migrationen laufen lassen. Einige
        # spaetere Tabellen werden nur durch Alembic-Versionen erzeugt.
        Base.metadata.create_all(engine)
        try:
            command.stamp(alembic_cfg, "beb242bcd1fb")
            logger.info("init_db(): Fresh-DB initialisiert + Alembic-Baseline gestempelt.")
            _run_alembic_migrations()
        except Exception as e:  # broad catch intentional — stamp ist optional
            logger.warning("Alembic-Upgrade auf Fresh-DB fehlgeschlagen: %s", e)
    else:
        # Existing-DB: Legacy-Migrations bringen aelteres Schema auf Baseline-Stand.
        # Danach Alembic-Migrations fuer alle nachfolgenden Schema-Aenderungen.
        Base.metadata.create_all(engine)  # Safety-Net fuer fehlende Tabellen
        _run_legacy_migrations()
        try:
            if not has_alembic_table:
                # Erste Alembic-Begegnung — als Baseline stempeln,
                # dann auf Head upgraden.
                command.stamp(alembic_cfg, "beb242bcd1fb")
                logger.info("init_db(): alembic_version-Tabelle als Baseline gestempelt.")
            _run_alembic_migrations()
        except Exception as e:  # broad catch intentional — Alembic errors must not block app startup
            logger.critical(
                "Alembic-Migration fehlgeschlagen (App startet trotzdem mit alter Schema-Version): %s",
                e,
            )
            # VAD-83 FIX: Dispose engine to release any write-locked connections
            # left by a failed Alembic migration (e.g., CREATE TABLE on existing table).
            try:
                engine.dispose()
            except Exception:
                pass

    # Seed default data
    _seed_defaults()


def _alembic_config():
    """Build Alembic Config object zentral fuer init_db + _run_alembic_migrations."""
    from alembic.config import Config

    alembic_ini = _REPO_ROOT / "alembic.ini"
    if alembic_ini.exists():
        cfg = Config(str(alembic_ini))
    else:
        cfg = Config()
    cfg.set_main_option(
        "script_location", str(_REPO_ROOT / "database" / "alembic")
    )
    cfg.set_main_option(
        "sqlalchemy.url", str(engine.url)
    )
    return cfg
