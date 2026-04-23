"""add_memory_layer_tables

Revision ID: 15b79edf1d76
Revises: b5d5adc80d3a
Create Date: 2026-04-23 13:05:48.126302

Adds the mem_* layer tables:
  - mem_pacing_run          (one row per agent pacing run)
  - mem_decision            (one row per cut decision; denormalised snapshot)
  - mem_learned_pattern     (aggregated patterns; Wilson-confidence)
  - mem_user_feedback_event (raw feedback events)
Plus all required indexes per Design §4.2.

Feasibility R4 addition: mem_decision.at_enricher_version TEXT
so pattern aggregator can ignore stale-version snapshots after re-clustering.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15b79edf1d76'
down_revision: Union[str, None] = 'b5d5adc80d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create mem_pacing_run, mem_decision, mem_learned_pattern, mem_user_feedback_event + indexes."""

    # ── mem_pacing_run ───────────────────────────────────────────────────────
    # One row per pacing run; FK to audio_tracks without CASCADE so deleting a
    # track does NOT wipe run history.
    op.create_table(
        "mem_pacing_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audio_track_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("is_dj_mix", sa.Boolean(), nullable=False),
        sa.Column("total_duration_sec", sa.Float(), nullable=False),
        sa.Column("total_cuts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("agent_version", sa.Text(), nullable=False),
        sa.Column("weights_profile", sa.Text(), nullable=False),
        sa.Column("user_rating", sa.Integer(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("steer_snapshot", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["audio_track_id"], ["audio_tracks.id"]),
    )

    # ── mem_decision ─────────────────────────────────────────────────────────
    # One row per cut decision; denormalised context snapshot (immutable truth).
    # FK run_id → CASCADE so deleting a run removes its decisions.
    # FK scene_id → NO CASCADE so deleted clips don't wipe history.
    # Feasibility R4: at_enricher_version TEXT so aggregator can skip stale rows.
    op.create_table(
        "mem_decision",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("sequence_idx", sa.Integer(), nullable=False),

        # WHEN in the mix
        sa.Column("at_timestamp_sec", sa.Float(), nullable=False),
        sa.Column("at_beat_idx", sa.Integer(), nullable=True),
        sa.Column("at_structure_segment_id", sa.Integer(), nullable=True),

        # AUDIO context snapshot
        sa.Column("at_bpm", sa.Float(), nullable=True),
        sa.Column("at_energy", sa.Float(), nullable=True),
        sa.Column("at_section_type", sa.Text(), nullable=True),
        sa.Column("at_key", sa.Text(), nullable=True),
        sa.Column("at_key_confidence", sa.Float(), nullable=True),
        sa.Column("at_key_modulation", sa.Boolean(), nullable=True),
        sa.Column("at_harmonic_tension", sa.Float(), nullable=True),
        sa.Column("at_mood_audio", sa.Text(), nullable=True),
        sa.Column("at_genre", sa.Text(), nullable=True),
        sa.Column("at_sub_genre", sa.Text(), nullable=True),
        sa.Column("at_spectral_hash", sa.Text(), nullable=True),
        sa.Column("at_groove_template", sa.Text(), nullable=True),
        sa.Column("at_lufs", sa.Float(), nullable=True),
        # Feasibility R4 addition — version-aware snapshot
        sa.Column("at_enricher_version", sa.Text(), nullable=True),

        # VIDEO context snapshot
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("clip_role", sa.Text(), nullable=False),
        sa.Column("clip_mood_refined", sa.Text(), nullable=False),
        sa.Column("clip_style_bucket_id", sa.Integer(), nullable=False),
        sa.Column("clip_motion_score", sa.Float(), nullable=True),

        # DECISION
        sa.Column("agent_score", sa.Float(), nullable=False),
        sa.Column("agent_rationale", sa.JSON(), nullable=False),

        # FEEDBACK
        sa.Column("user_verdict", sa.Text(), nullable=True),
        sa.Column("user_verdict_at", sa.DateTime(), nullable=True),
        sa.Column("user_rating", sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["mem_pacing_run.id"], ondelete="CASCADE"
        ),
        # No CASCADE on scene_id: deleted clips must not wipe decision history.
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
    )
    op.create_index("idx_mem_decision_run", "mem_decision", ["run_id", "sequence_idx"])
    op.create_index("idx_mem_decision_scene", "mem_decision", ["scene_id"])
    op.create_index("idx_mem_decision_verdict", "mem_decision", ["user_verdict"])
    op.create_index(
        "idx_mem_decision_context_hash",
        "mem_decision",
        ["at_genre", "at_section_type", "at_bpm"],
    )

    # ── mem_learned_pattern ──────────────────────────────────────────────────
    op.create_table(
        "mem_learned_pattern",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pattern_type", sa.Text(), nullable=False),
        sa.Column("context_fingerprint", sa.JSON(), nullable=True),
        sa.Column("target_ref", sa.JSON(), nullable=True),
        sa.Column("stat_accept_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stat_reject_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stat_sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_mem_learned_pattern_type", "mem_learned_pattern", ["pattern_type"])

    # ── mem_user_feedback_event ──────────────────────────────────────────────
    # Raw append-only feedback events.
    # FK run_id → CASCADE so run deletion removes its events.
    # FK decision_id → nullable, no CASCADE (audit trail remains even if
    # decision row is somehow gone).
    op.create_table(
        "mem_user_feedback_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["mem_pacing_run.id"], ondelete="CASCADE"
        ),
        # decision_id FK without CASCADE (nullable, audit trail)
        sa.ForeignKeyConstraint(["decision_id"], ["mem_decision.id"]),
    )


def downgrade() -> None:
    """Drop mem_user_feedback_event, mem_decision, mem_learned_pattern, mem_pacing_run + all indexes."""

    # Drop child-first to respect FK constraints.
    op.drop_table("mem_user_feedback_event")

    op.drop_index("idx_mem_decision_context_hash", table_name="mem_decision")
    op.drop_index("idx_mem_decision_verdict", table_name="mem_decision")
    op.drop_index("idx_mem_decision_scene", table_name="mem_decision")
    op.drop_index("idx_mem_decision_run", table_name="mem_decision")
    op.drop_table("mem_decision")

    op.drop_index("idx_mem_learned_pattern_type", table_name="mem_learned_pattern")
    op.drop_table("mem_learned_pattern")

    op.drop_table("mem_pacing_run")
