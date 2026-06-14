"""add storage provenance tables

Revision ID: e5f6a7b8c9d0
Revises: 9da529c08d55
Create Date: 2026-06-14

GLOBAL-STORAGE-PROVENANCE-2026-05-19 / OTK-021 Tier 1:

- analysis_jobs
- analysis_artifacts
- step_deps
- project_sources

Idempotent because production startup may create tables from current
Base.metadata before Alembic runs.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "9da529c08d55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    rows = bind.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
    return any(row[1] == index_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "analysis_jobs"):
        op.create_table(
            "analysis_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_sha256", sa.String(), nullable=False),
            sa.Column("step_id", sa.String(), nullable=False),
            sa.Column("step_version", sa.String(), nullable=False),
            sa.Column("params_hash", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("produced_by_model", sa.String(), nullable=True),
            sa.Column("produced_by_model_version", sa.String(), nullable=True),
            sa.Column("coverage_percent", sa.Float(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "analysis_jobs", "uq_analysis_jobs_identity"):
        op.create_index(
            "uq_analysis_jobs_identity",
            "analysis_jobs",
            ["source_sha256", "step_id", "step_version", "params_hash"],
            unique=True,
        )
    if not _index_exists(bind, "analysis_jobs", "ix_analysis_jobs_source_sha256"):
        op.create_index("ix_analysis_jobs_source_sha256", "analysis_jobs", ["source_sha256"])
    if not _index_exists(bind, "analysis_jobs", "ix_analysis_jobs_status"):
        op.create_index("ix_analysis_jobs_status", "analysis_jobs", ["status"])

    if not _table_exists(bind, "analysis_artifacts"):
        op.create_table(
            "analysis_artifacts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("artifact_type", sa.String(), nullable=False),
            sa.Column("artifact_role", sa.String(), nullable=False),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("bytes", sa.BigInteger(), nullable=True),
            sa.Column("sha256", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        )
    if not _index_exists(bind, "analysis_artifacts", "ix_analysis_artifacts_job_id"):
        op.create_index("ix_analysis_artifacts_job_id", "analysis_artifacts", ["job_id"])
    if not _index_exists(bind, "analysis_artifacts", "ix_analysis_artifacts_role"):
        op.create_index("ix_analysis_artifacts_role", "analysis_artifacts", ["artifact_role"])

    if not _table_exists(bind, "step_deps"):
        op.create_table(
            "step_deps",
            sa.Column("step_id", sa.String(), nullable=False),
            sa.Column("depends_on_step_id", sa.String(), nullable=False),
            sa.Column("uses_artifact_role", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("step_id", "depends_on_step_id"),
        )

    if not _table_exists(bind, "project_sources"):
        op.create_table(
            "project_sources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("source_sha256", sa.String(), nullable=False),
            sa.Column("current_source_path", sa.String(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
    if not _index_exists(bind, "project_sources", "uq_project_sources_project_source"):
        op.create_index(
            "uq_project_sources_project_source",
            "project_sources",
            ["project_id", "source_sha256"],
            unique=True,
        )
    if not _index_exists(bind, "project_sources", "ix_project_sources_source_sha256"):
        op.create_index("ix_project_sources_source_sha256", "project_sources", ["source_sha256"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "project_sources"):
        if _index_exists(bind, "project_sources", "ix_project_sources_source_sha256"):
            op.drop_index("ix_project_sources_source_sha256", table_name="project_sources")
        if _index_exists(bind, "project_sources", "uq_project_sources_project_source"):
            op.drop_index("uq_project_sources_project_source", table_name="project_sources")
        op.drop_table("project_sources")

    if _table_exists(bind, "step_deps"):
        op.drop_table("step_deps")

    if _table_exists(bind, "analysis_artifacts"):
        if _index_exists(bind, "analysis_artifacts", "ix_analysis_artifacts_role"):
            op.drop_index("ix_analysis_artifacts_role", table_name="analysis_artifacts")
        if _index_exists(bind, "analysis_artifacts", "ix_analysis_artifacts_job_id"):
            op.drop_index("ix_analysis_artifacts_job_id", table_name="analysis_artifacts")
        op.drop_table("analysis_artifacts")

    if _table_exists(bind, "analysis_jobs"):
        if _index_exists(bind, "analysis_jobs", "ix_analysis_jobs_status"):
            op.drop_index("ix_analysis_jobs_status", table_name="analysis_jobs")
        if _index_exists(bind, "analysis_jobs", "ix_analysis_jobs_source_sha256"):
            op.drop_index("ix_analysis_jobs_source_sha256", table_name="analysis_jobs")
        if _index_exists(bind, "analysis_jobs", "uq_analysis_jobs_identity"):
            op.drop_index("uq_analysis_jobs_identity", table_name="analysis_jobs")
        op.drop_table("analysis_jobs")
