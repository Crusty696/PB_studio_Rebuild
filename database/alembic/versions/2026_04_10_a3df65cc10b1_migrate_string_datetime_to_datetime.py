"""Migrate string datetime columns to DateTime type (M-38)

Revision ID: a3df65cc10b1
Revises: da8d942ad38a
Create Date: 2026-04-10 14:00:00.000000

B-181 Fix (Cycle 1): Idempotency-Schutz hinzugefügt. Vorher führte die
Migration das DROP-/RENAME-Muster blind aus, auch wenn die Zielspalte
bereits DateTime-Typ hatte (Fall: Initial-Migration erstellt Schema neu
nach B-181-Fix). Jetzt überspringt jede Spalte ihre Konversion sobald der
deklarierte Typ ``DATETIME`` ist — kein unnötiger Datenverlust durch
strftime-Round-Trip.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'a3df65cc10b1'
down_revision: Union[str, None] = 'da8d942ad38a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_indexes_on_column(conn, table: str, column: str) -> list[dict]:
    """B-825: Indizes auf *column* entfernen und ihre Definition zurueckgeben.

    ``batch_alter_table`` baut eine SQLite-Tabelle beim ``drop_column`` komplett
    neu und legt dabei die zuvor reflektierten Indizes wieder an. Liegt ein
    Index auf genau der Spalte, die gerade verschwindet, scheitert das mit
    ``no such column``.

    Konkret aufgefallen an ``idx_model_registry_last_used``: der Index kam mit
    B-819 kanonisch in ``database/models.py`` dazu, seitdem war der
    ``downgrade()``-Pfad dieser Revision gebrochen und
    ``test_full_roundtrip_empty_db`` rot. Vor B-819 gab es den Index nicht,
    deshalb lief es vorher.

    Die zurueckgegebenen Definitionen erlauben dem Aufrufer, die Indizes nach
    dem Umbenennen der Ersatzspalte wiederherzustellen — sonst verlaere ein
    Downgrade sie stillschweigend.
    """
    inspector = sa.inspect(conn)
    try:
        indexes = inspector.get_indexes(table)
    except Exception:  # pragma: no cover - Tabelle fehlt
        return []
    betroffen = [
        idx for idx in indexes
        if column in (idx.get("column_names") or [])
    ]
    for idx in betroffen:
        name = idx.get("name")
        if not name:
            continue
        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
    return betroffen


def _recreate_indexes(conn, table: str, indexes: list[dict]) -> None:
    """B-825: Gegenstueck zu :func:`_drop_indexes_on_column`."""
    for idx in indexes:
        name = idx.get("name")
        cols = idx.get("column_names") or []
        if not name or not cols:
            continue
        unique = "UNIQUE " if idx.get("unique") else ""
        spalten = ", ".join(f'"{c}"' for c in cols)
        conn.execute(text(
            f'CREATE {unique}INDEX IF NOT EXISTS "{name}" ON {table} ({spalten})'
        ))


def _column_is_datetime(inspector: sa.engine.reflection.Inspector,
                         table: str, column: str) -> bool:
    """True wenn Spalte existiert und der deklarierte Typ DateTime ist.

    SQLite ist typeless, aber speichert den deklarierten Typ-Affinity-String.
    SQLAlchemy reflektiert ``DATETIME``/``TIMESTAMP`` als ``sa.DateTime``.
    Eine als String/TEXT deklarierte Spalte wird hingegen als ``sa.Text``
    oder ``sa.String`` zurückgegeben — der Konversionspfad bleibt dafür
    aktiv.
    """
    try:
        cols = {c["name"]: c["type"] for c in inspector.get_columns(table)}
    except Exception:
        return False
    if column not in cols:
        return False
    return isinstance(cols[column], sa.DateTime)


def upgrade() -> None:
    """Convert String datetime columns to proper DateTime type.

    Affected tables and columns:
    - ai_pacing_memory.created_at
    - agent_feedback.created_at
    - model_registry.installed_at
    - model_registry.last_used_at

    SQLite doesn't support ALTER COLUMN TYPE, so we:
    1. Add new DateTime columns with _new suffix
    2. Copy and convert data from String to DateTime
    3. Drop old String columns
    4. Rename new columns to original names

    B-181: Idempotent — überspringt Spalten die bereits als DateTime
    deklariert sind (Fall: frische DB nach Initial-Migration).
    """
    conn = op.get_bind()

    # Check if tables exist before migration
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Migrate ai_pacing_memory.created_at
    if 'ai_pacing_memory' in existing_tables and not _column_is_datetime(
        inspector, 'ai_pacing_memory', 'created_at'
    ):
        columns = {c['name'] for c in inspector.get_columns('ai_pacing_memory')}

        # Step 1: Add new DateTime column if it doesn't exist
        if 'created_at_new' not in columns:
            op.add_column('ai_pacing_memory', sa.Column('created_at_new', sa.DateTime(), nullable=True))

        # Step 2: If old column still exists, copy data and complete migration
        if 'created_at' in columns:
            # Refresh column list after potential add
            columns = {c['name'] for c in inspector.get_columns('ai_pacing_memory')}

            # Copy data: parse ISO strings to datetime (SQLite understands ISO format natively)
            conn.execute(text("""
                UPDATE ai_pacing_memory
                SET created_at_new = datetime(created_at)
                WHERE created_at IS NOT NULL AND created_at != ''
            """))

            # Drop old column (SQLite 3.35+)
            conn.execute(text('ALTER TABLE ai_pacing_memory DROP COLUMN created_at'))

            # Rename new column to original name (SQLite 3.25+)
            conn.execute(text('ALTER TABLE ai_pacing_memory RENAME COLUMN created_at_new TO created_at'))

    # Migrate agent_feedback.created_at
    if 'agent_feedback' in existing_tables and not _column_is_datetime(
        inspector, 'agent_feedback', 'created_at'
    ):
        columns = {c['name'] for c in inspector.get_columns('agent_feedback')}

        # Step 1: Add new DateTime column if it doesn't exist
        if 'created_at_new' not in columns:
            op.add_column('agent_feedback', sa.Column('created_at_new', sa.DateTime(), nullable=True))

        # Step 2: If old column still exists, copy data and complete migration
        if 'created_at' in columns:
            columns = {c['name'] for c in inspector.get_columns('agent_feedback')}

            conn.execute(text("""
                UPDATE agent_feedback
                SET created_at_new = datetime(created_at)
                WHERE created_at IS NOT NULL AND created_at != ''
            """))

            conn.execute(text('ALTER TABLE agent_feedback DROP COLUMN created_at'))
            conn.execute(text('ALTER TABLE agent_feedback RENAME COLUMN created_at_new TO created_at'))

    # Migrate model_registry.installed_at + last_used_at
    if 'model_registry' in existing_tables:
        # installed_at: nur konvertieren wenn noch String
        if not _column_is_datetime(inspector, 'model_registry', 'installed_at'):
            columns = {c['name'] for c in inspector.get_columns('model_registry')}

            # Step 1: Add new DateTime column if it doesn't exist
            if 'installed_at_new' not in columns:
                op.add_column('model_registry', sa.Column('installed_at_new', sa.DateTime(), nullable=True))

            # Step 2: If old column still exists, copy data and complete migration
            if 'installed_at' in columns:
                columns = {c['name'] for c in inspector.get_columns('model_registry')}

                conn.execute(text("""
                    UPDATE model_registry
                    SET installed_at_new = datetime(installed_at)
                    WHERE installed_at IS NOT NULL AND installed_at != ''
                """))

                conn.execute(text('ALTER TABLE model_registry DROP COLUMN installed_at'))
                conn.execute(text('ALTER TABLE model_registry RENAME COLUMN installed_at_new TO installed_at'))

        # last_used_at: nur konvertieren wenn noch String
        if not _column_is_datetime(inspector, 'model_registry', 'last_used_at'):
            columns = {c['name'] for c in inspector.get_columns('model_registry')}

            # Step 1: Add new DateTime column if it doesn't exist
            if 'last_used_at_new' not in columns:
                op.add_column('model_registry', sa.Column('last_used_at_new', sa.DateTime(), nullable=True))

            # Step 2: If old column still exists, copy data and complete migration
            if 'last_used_at' in columns:
                columns = {c['name'] for c in inspector.get_columns('model_registry')}

                conn.execute(text("""
                    UPDATE model_registry
                    SET last_used_at_new = datetime(last_used_at)
                    WHERE last_used_at IS NOT NULL AND last_used_at != ''
                """))

                # Drop index on last_used_at before dropping the column
                conn.execute(text('DROP INDEX IF EXISTS ix_model_registry_last_used'))

                conn.execute(text('ALTER TABLE model_registry DROP COLUMN last_used_at'))
                conn.execute(text('ALTER TABLE model_registry RENAME COLUMN last_used_at_new TO last_used_at'))

                # Recreate the index on the renamed column
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_model_registry_last_used ON model_registry(last_used_at)'))


def downgrade() -> None:
    """Convert DateTime columns back to String (ISO format).

    This is a lossy conversion but maintains data in ISO 8601 format.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Reverse ai_pacing_memory.created_at
    if 'ai_pacing_memory' in existing_tables:
        columns = {c['name'] for c in inspector.get_columns('ai_pacing_memory')}
        if 'created_at' in columns:
            op.add_column('ai_pacing_memory', sa.Column('created_at_new', sa.String(), nullable=True))

            conn.execute(text("""
                UPDATE ai_pacing_memory
                SET created_at_new = strftime('%Y-%m-%dT%H:%M:%S', created_at)
                WHERE created_at IS NOT NULL
            """))

            # B-825: Indizes auf der Spalte muessen weg, bevor
            # batch_alter_table die Tabelle ohne sie neu baut.
            _idx = _drop_indexes_on_column(conn, 'ai_pacing_memory', 'created_at')

            with op.batch_alter_table('ai_pacing_memory', schema=None) as batch_op:
                batch_op.drop_column('created_at')

            with op.batch_alter_table('ai_pacing_memory', schema=None) as batch_op:
                batch_op.alter_column('created_at_new', new_column_name='created_at')

            _recreate_indexes(conn, 'ai_pacing_memory', _idx)

    # Reverse agent_feedback.created_at
    if 'agent_feedback' in existing_tables:
        columns = {c['name'] for c in inspector.get_columns('agent_feedback')}
        if 'created_at' in columns:
            op.add_column('agent_feedback', sa.Column('created_at_new', sa.String(), nullable=True))

            conn.execute(text("""
                UPDATE agent_feedback
                SET created_at_new = strftime('%Y-%m-%dT%H:%M:%S', created_at)
                WHERE created_at IS NOT NULL
            """))

            # B-825: Indizes auf der Spalte muessen weg, bevor
            # batch_alter_table die Tabelle ohne sie neu baut.
            _idx = _drop_indexes_on_column(conn, 'agent_feedback', 'created_at')

            with op.batch_alter_table('agent_feedback', schema=None) as batch_op:
                batch_op.drop_column('created_at')

            with op.batch_alter_table('agent_feedback', schema=None) as batch_op:
                batch_op.alter_column('created_at_new', new_column_name='created_at')

            _recreate_indexes(conn, 'agent_feedback', _idx)

    # Reverse model_registry datetime columns
    if 'model_registry' in existing_tables:
        columns = {c['name'] for c in inspector.get_columns('model_registry')}
        if 'installed_at' in columns:
            op.add_column('model_registry', sa.Column('installed_at_new', sa.String(), nullable=True))

            conn.execute(text("""
                UPDATE model_registry
                SET installed_at_new = strftime('%Y-%m-%dT%H:%M:%S', installed_at)
                WHERE installed_at IS NOT NULL
            """))

            # B-825: Indizes auf der Spalte muessen weg, bevor
            # batch_alter_table die Tabelle ohne sie neu baut.
            _idx = _drop_indexes_on_column(conn, 'model_registry', 'installed_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.drop_column('installed_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.alter_column('installed_at_new', new_column_name='installed_at')

            _recreate_indexes(conn, 'model_registry', _idx)

        if 'last_used_at' in columns:
            op.add_column('model_registry', sa.Column('last_used_at_new', sa.String(), nullable=True))

            conn.execute(text("""
                UPDATE model_registry
                SET last_used_at_new = strftime('%Y-%m-%dT%H:%M:%S', last_used_at)
                WHERE last_used_at IS NOT NULL
            """))

            # B-825: Indizes auf der Spalte muessen weg, bevor
            # batch_alter_table die Tabelle ohne sie neu baut.
            _idx = _drop_indexes_on_column(conn, 'model_registry', 'last_used_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.drop_column('last_used_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.alter_column('last_used_at_new', new_column_name='last_used_at')

            _recreate_indexes(conn, 'model_registry', _idx)
