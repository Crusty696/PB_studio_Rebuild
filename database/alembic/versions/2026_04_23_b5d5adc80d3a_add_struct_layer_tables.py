"""add_struct_layer_tables

Revision ID: b5d5adc80d3a
Revises: a3df65cc10b1
Create Date: 2026-04-23 13:04:24.984718

Adds the struct_* layer tables:
  - struct_style_bucket  (style clusters with active flag — Feasibility R4)
  - struct_clip_tags     (per-scene enrichment tags; FK to scenes + struct_style_bucket)
  - struct_compat_edge   (pairwise cosine-similarity graph; FK to scenes)
Plus all required indexes per Design §4.1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d5adc80d3a'
down_revision: Union[str, None] = 'a3df65cc10b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create struct_style_bucket, struct_clip_tags, struct_compat_edge + indexes."""

    # ── struct_style_bucket ──────────────────────────────────────────────────
    # Parent table — must be created before struct_clip_tags (FK dependency).
    # `active` column is the Feasibility-R4 addition (version-aware bucket
    # lifecycle: old buckets stay in schema so historical mem_decision rows
    # can reference them; UI shows only active=1 buckets).
    op.create_table(
        "struct_style_bucket",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("centroid_embedding", sa.LargeBinary(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("enricher_version", sa.Text(), nullable=False),
        # Feasibility R4 addition: lets UI filter out stale buckets after re-clustering
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_struct_style_bucket_name"),
    )

    # ── struct_clip_tags ─────────────────────────────────────────────────────
    # Per-scene enrichment output; scene_id is the PK (one row per scene).
    # FK to scenes(id) with CASCADE so deleting a clip removes its tags.
    # FK to struct_style_bucket(id) without CASCADE so deleted buckets keep
    # historical tag rows accessible.
    op.create_table(
        "struct_clip_tags",
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("role_confidence", sa.Float(), nullable=False),
        sa.Column("mood_refined", sa.Text(), nullable=False),
        sa.Column("mood_confidence", sa.Float(), nullable=False),
        sa.Column("style_bucket_id", sa.Integer(), nullable=False),
        sa.Column("style_distance", sa.Float(), nullable=False),
        sa.Column("enriched_at", sa.DateTime(), nullable=False),
        sa.Column("enricher_version", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("scene_id"),
        sa.ForeignKeyConstraint(
            ["scene_id"], ["scenes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["style_bucket_id"], ["struct_style_bucket.id"]
        ),
    )
    op.create_index("idx_struct_clip_tags_role", "struct_clip_tags", ["role"])
    op.create_index("idx_struct_clip_tags_mood", "struct_clip_tags", ["mood_refined"])
    op.create_index("idx_struct_clip_tags_style", "struct_clip_tags", ["style_bucket_id"])

    # ── struct_compat_edge ───────────────────────────────────────────────────
    # Pairwise cosine-similarity graph edges; composite PK (scene_id_a, scene_id_b).
    # Both FKs CASCADE so orphaned edges are cleaned up automatically.
    op.create_table(
        "struct_compat_edge",
        sa.Column("scene_id_a", sa.Integer(), nullable=False),
        sa.Column("scene_id_b", sa.Integer(), nullable=False),
        sa.Column("cosine_similarity", sa.Float(), nullable=False),
        sa.Column("rank_in_a", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("scene_id_a", "scene_id_b"),
        sa.ForeignKeyConstraint(
            ["scene_id_a"], ["scenes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scene_id_b"], ["scenes.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "idx_struct_compat_edge_a_rank",
        "struct_compat_edge",
        ["scene_id_a", "rank_in_a"],
    )


def downgrade() -> None:
    """Drop struct_compat_edge, struct_clip_tags, struct_style_bucket + all indexes."""

    # Drop child tables first (FK dependency order), then parent.
    op.drop_index("idx_struct_compat_edge_a_rank", table_name="struct_compat_edge")
    op.drop_table("struct_compat_edge")

    op.drop_index("idx_struct_clip_tags_style", table_name="struct_clip_tags")
    op.drop_index("idx_struct_clip_tags_mood", table_name="struct_clip_tags")
    op.drop_index("idx_struct_clip_tags_role", table_name="struct_clip_tags")
    op.drop_table("struct_clip_tags")

    op.drop_table("struct_style_bucket")
