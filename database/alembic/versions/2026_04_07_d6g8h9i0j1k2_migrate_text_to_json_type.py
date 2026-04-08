"""Migrate Text columns to JSON type for JSON data

Revision ID: d6g8h9i0j1k2
Revises: c5f6g7h8i9j0
Create Date: 2026-04-07 03:05:00.000000

P1.7-FIX: Convert Text columns storing JSON data to proper JSON type.

For SQLite: This is a documentation-only migration. SQLite stores both TEXT and JSON
as TEXT type at the database level. The change is at the SQLAlchemy ORM level only,
enabling automatic JSON serialization/deserialization and validation.

Affected columns (21 total):
- AudioTrack: energy_curve, spectral_bands, key_modulation_data, harmonic_tension_curve
- Scene: ai_caption, ai_tags
- Beatgrid: beat_positions, downbeat_positions, energy_per_beat, stem_weighted_energy,
           onset_kick_data, onset_snare_data, onset_hihat_data
- WaveformData: band_low, band_mid, band_high
- PacingBlueprint: energy_curve
- AIPacingMemory: siglip_tags
- ModelRegistry: metadata_json

Benefits:
1. Automatic JSON serialization/deserialization (no manual json.loads/dumps)
2. Type safety - ensures only valid JSON is stored
3. Better intent in schema - clearly marks JSON columns
4. Foundation for future Pydantic validation layer

No database schema changes required for SQLite.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6g8h9i0j1k2'
down_revision = 'c5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    No database schema changes for SQLite.

    The JSON type in SQLAlchemy maps to TEXT in SQLite, same as the Text type.
    All changes are at the ORM level only (models.py).

    If migrating to PostgreSQL in the future, this migration should be updated
    to use ALTER TABLE ... ALTER COLUMN ... TYPE jsonb.
    """
    pass


def downgrade() -> None:
    """
    No database schema changes to revert.

    To fully downgrade, you would need to revert models.py to use Text type
    instead of JSON type for the affected columns.
    """
    pass
