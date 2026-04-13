"""Migrate string datetime columns to DateTime type (M-38)

Revision ID: a3df65cc10b1
Revises: da8d942ad38a
Create Date: 2026-04-10 14:00:00.000000
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
    """
    conn = op.get_bind()

    # Check if tables exist before migration
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Migrate ai_pacing_memory.created_at
    if 'ai_pacing_memory' in existing_tables:
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
    if 'agent_feedback' in existing_tables:
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

    # Migrate model_registry.installed_at
    if 'model_registry' in existing_tables:
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

        # Migrate model_registry.last_used_at
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

            with op.batch_alter_table('ai_pacing_memory', schema=None) as batch_op:
                batch_op.drop_column('created_at')

            with op.batch_alter_table('ai_pacing_memory', schema=None) as batch_op:
                batch_op.alter_column('created_at_new', new_column_name='created_at')

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

            with op.batch_alter_table('agent_feedback', schema=None) as batch_op:
                batch_op.drop_column('created_at')

            with op.batch_alter_table('agent_feedback', schema=None) as batch_op:
                batch_op.alter_column('created_at_new', new_column_name='created_at')

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

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.drop_column('installed_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.alter_column('installed_at_new', new_column_name='installed_at')

        if 'last_used_at' in columns:
            op.add_column('model_registry', sa.Column('last_used_at_new', sa.String(), nullable=True))

            conn.execute(text("""
                UPDATE model_registry
                SET last_used_at_new = strftime('%Y-%m-%dT%H:%M:%S', last_used_at)
                WHERE last_used_at IS NOT NULL
            """))

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.drop_column('last_used_at')

            with op.batch_alter_table('model_registry', schema=None) as batch_op:
                batch_op.alter_column('last_used_at_new', new_column_name='last_used_at')
