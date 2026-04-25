"""add_reward_components_to_mem_decision

Revision ID: a1b2c3d4e5f6
Revises: e670c6bc097c
Create Date: 2026-04-26

P1.3 / Cycle 11: Erweitert mem_decision um zwei Spalten für die
RL-Multi-Objective-Reward-Pipeline (Slice 4):

- reward (Float, nullable) — gewichtete Summe der 7 Komponenten ∈ [0, 1].
  Kann nullable sein, weil ältere Decisions vor diesem Sprint sie nicht
  haben.
- reward_components (JSON, nullable) — Breakdown aller 7 Sub-Rewards
  (r_energy, r_mood, r_stem_class, r_section, r_freshness, r_collision,
  r_user). Wird vom Decision-Explorer-Widget gelesen.

Idempotency: SQLite ALTER TABLE ADD COLUMN ist idempotent durch
information_schema-Lookup; vermeidet Re-Run-Fehler.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger("alembic.migrate.add_reward_components_to_mem_decision")

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e670c6bc097c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    """SQLite-aware column-exists check (PRAGMA table_info)."""
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "mem_decision", "reward"):
        op.add_column(
            "mem_decision",
            sa.Column("reward", sa.Float(), nullable=True),
        )
        logger.info("Added mem_decision.reward")
    else:
        logger.info("mem_decision.reward already exists — skipping")

    if not _column_exists(bind, "mem_decision", "reward_components"):
        op.add_column(
            "mem_decision",
            sa.Column("reward_components", sa.JSON(), nullable=True),
        )
        logger.info("Added mem_decision.reward_components")
    else:
        logger.info("mem_decision.reward_components already exists — skipping")


def downgrade() -> None:
    """Entfernt die zwei Spalten wieder.

    SQLite ≥ 3.35 unterstützt DROP COLUMN nativ. Falls auf älterer
    Version: Migration ist additive Daten-Zusatzinfo, ein Downgrade ohne
    DROP funktional ok (Spalten bleiben unbenutzt).
    """
    bind = op.get_bind()

    if _column_exists(bind, "mem_decision", "reward_components"):
        try:
            op.drop_column("mem_decision", "reward_components")
        except Exception as e:  # broad: SQLite vor 3.35 wirft hier
            logger.warning(
                "drop_column reward_components fehlgeschlagen (SQLite < 3.35?): %s. "
                "Spalte bleibt — funktional unkritisch.", e,
            )

    if _column_exists(bind, "mem_decision", "reward"):
        try:
            op.drop_column("mem_decision", "reward")
        except Exception as e:
            logger.warning(
                "drop_column reward fehlgeschlagen (SQLite < 3.35?): %s. "
                "Spalte bleibt — funktional unkritisch.", e,
            )
