"""add_brain_v2_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-30

Adds app-internal Studio Brain v2 tables. These tables are product runtime
state and do not depend on Brain-Bug/Obsidian.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brain_entity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "source_table", "source_id", name="uq_brain_entity_source"),
    )
    op.create_index("idx_brain_entity_type", "brain_entity", ["entity_type"])

    op.create_table(
        "brain_fact",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["entity_id"], ["brain_entity.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_brain_fact_entity", "brain_fact", ["entity_id"])
    op.create_index("idx_brain_fact_key", "brain_fact", ["key"])

    op.create_table(
        "brain_decision",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("audio_entity_id", sa.Integer(), nullable=True),
        sa.Column("clip_entity_id", sa.Integer(), nullable=True),
        sa.Column("why_json", sa.Text(), nullable=False),
        sa.Column("why_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", name="uq_brain_decision_mem_decision"),
        sa.ForeignKeyConstraint(["audio_entity_id"], ["brain_entity.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["clip_entity_id"], ["brain_entity.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_brain_decision_run", "brain_decision", ["run_id"])

    op.create_table(
        "brain_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_type", "scope", name="uq_brain_memory_scope"),
    )
    op.create_index("idx_brain_memory_scope", "brain_memory", ["scope"])

    op.create_table(
        "brain_note",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("linked_entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title", "source", name="uq_brain_note_title_source"),
        sa.ForeignKeyConstraint(["linked_entity_id"], ["brain_entity.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("brain_note")
    op.drop_index("idx_brain_memory_scope", table_name="brain_memory")
    op.drop_table("brain_memory")
    op.drop_index("idx_brain_decision_run", table_name="brain_decision")
    op.drop_table("brain_decision")
    op.drop_index("idx_brain_fact_key", table_name="brain_fact")
    op.drop_index("idx_brain_fact_entity", table_name="brain_fact")
    op.drop_table("brain_fact")
    op.drop_index("idx_brain_entity_type", table_name="brain_entity")
    op.drop_table("brain_entity")
