"""drop_unused_brain_v2_tables

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-27

Brain-Bereinigung (User-Entscheidung 2026-08-27, Scope "Nur Totes +
Inaktives"): Die Brain-V2-Tabellen ``brain_entity``, ``brain_fact``,
``brain_decision`` und ``brain_memory`` aus Revision c3d4e5f6a7b8 wurden
seit ihrer Anlage von keinem Code beschrieben oder gelesen (0 Reads,
0 Writes, verifiziert per Repo-Grep am 2026-08-27). Sie werden entfernt.

``brain_note`` bleibt bestehen — es ist die einzige V2-Tabelle mit einem
echten Nutzer (``brain_learn_note`` / ``brain_recall`` in
``services/actions/brain_actions.py``). Die Spalte
``brain_note.linked_entity_id`` bleibt unveraendert erhalten: ihr
FK-Ziel ``brain_entity`` hatte immer 0 Zeilen, ein Nicht-NULL-Wert war
also schon bisher nie gueltig einfuegbar; produktiv wird ausschliesslich
NULL geschrieben. Ein Tabellen-Rebuild von ``brain_note`` nur zum
Entfernen der toten Spalte waere riskanter als der Status quo.

Drop-Reihenfolge: Kind-Tabellen zuerst (brain_fact/brain_decision/
brain_memory referenzieren brain_entity). Defensive Existenz-Pruefung,
weil aeltere Datenbanken die Kette unterschiedlich weit gelaufen sein
koennen.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def _existing_tables() -> set:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "brain_memory" in existing:
        op.drop_index("idx_brain_memory_scope", table_name="brain_memory")
        op.drop_table("brain_memory")
    if "brain_decision" in existing:
        op.drop_index("idx_brain_decision_run", table_name="brain_decision")
        op.drop_table("brain_decision")
    if "brain_fact" in existing:
        op.drop_index("idx_brain_fact_key", table_name="brain_fact")
        op.drop_index("idx_brain_fact_entity", table_name="brain_fact")
        op.drop_table("brain_fact")
    if "brain_entity" in existing:
        op.drop_index("idx_brain_entity_type", table_name="brain_entity")
        op.drop_table("brain_entity")


def downgrade() -> None:
    # Wiederherstellung identisch zu c3d4e5f6a7b8 (ohne brain_note, die
    # hier nicht angefasst wird). Daten sind nicht wiederherstellbar —
    # es gab nie welche.
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
        sa.UniqueConstraint(
            "entity_type", "source_table", "source_id",
            name="uq_brain_entity_source",
        ),
    )
    op.create_index("idx_brain_entity_type", "brain_entity", ["entity_type"])

    op.create_table(
        "brain_fact",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column(
            "confidence", sa.Float(), nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["brain_entity.id"], ondelete="CASCADE",
        ),
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
        sa.ForeignKeyConstraint(
            ["audio_entity_id"], ["brain_entity.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clip_entity_id"], ["brain_entity.id"], ondelete="SET NULL",
        ),
    )
    op.create_index("idx_brain_decision_run", "brain_decision", ["run_id"])

    op.create_table(
        "brain_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "confidence", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "positive_count", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "negative_count", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_type", "scope", name="uq_brain_memory_scope"),
    )
    op.create_index("idx_brain_memory_scope", "brain_memory", ["scope"])
