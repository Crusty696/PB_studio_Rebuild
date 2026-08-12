"""add_project_sources_stat_fingerprint

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-12

B-814 — Kurzschluss fuer die Quellen-Hashes beim Projekt-Open.

``StorageMigrationService.migrate_existing_outputs`` laeuft bei JEDEM
``open_project`` (``services/project_manager.py``) und berechnete pro
Audiotrack/Videoclip mit vorhandenen Outputs
``compute_source_sha256(..., mode="strict")`` — also einen SHA-256 ueber die
KOMPLETTE Quelldatei. An der realen Projekt-DB gemessen: 123 Clips /
1,16 GB, die bei jedem Oeffnen vollstaendig gelesen wurden.

Fuer die Artefakte existiert dieser Guard laengst
(``AnalysisArtifact.bytes``, siehe ``_upsert_artifact``): unveraenderte
Groesse + bereits gespeicherter Hash => nicht neu lesen. Fuer die QUELLEN
fehlte schlicht die Spalte, an der man das festmachen konnte —
``project_sources`` kannte nur ``source_sha256`` und
``current_source_path``.

Diese Revision ruestet den Stat-Fingerabdruck nach:

- ``source_bytes``     BIGINT  Dateigroesse in Bytes zum Hash-Zeitpunkt
- ``source_mtime_ns``  BIGINT  ``st_mtime_ns`` zum Hash-Zeitpunkt

Warum BEIDE und nicht nur die Groesse: Groesse allein wuerde eine
inhaltliche Aenderung bei exakt gleicher Byte-Zahl uebersehen. Die mtime
faengt genau diesen Fall ab, weil jedes normale Schreiben auf die Datei sie
mitzieht. Restrisiko und dessen Grenzen sind im Bugfile B-814 dokumentiert.

Beide Spalten NULLABLE: Bestandszeilen haben keinen Wert. NULL bedeutet
ehrlich "nie erfasst" und fuehrt zu genau einem regulaeren Hash-Lauf, der
den Wert nachtraegt (Selbstheilung, kein Backfill-Skript noetig).

FROZEN-Regel B-509: ``database/migrations.py`` ist eingefroren, neue
Schemaaenderungen ausschliesslich via Alembic — genau das ist diese Datei.
Kein Hand-ALTER im Legacy-Block.

SQLite via ``op.batch_alter_table``; idempotent per PRAGMA-Check, gleiches
Muster wie ``f2a3b4c5d6e7`` / ``c9d0e1f2a3b4``.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.add_project_sources_stat_fingerprint")

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "project_sources"

_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine]] = [
    ("source_bytes", sa.BigInteger()),
    ("source_mtime_ns", sa.BigInteger()),
]


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        logger.info(
            "%s fehlt — uebersprungen (frische DB legt sie via e5f6a7b8c9d0 an)",
            _TABLE,
        )
        return

    missing = [
        (name, type_)
        for name, type_ in _NEW_COLUMNS
        if not _column_exists(bind, _TABLE, name)
    ]
    if not missing:
        logger.info("%s: Stat-Fingerabdruck-Spalten vorhanden — skip", _TABLE)
        return

    with op.batch_alter_table(_TABLE) as batch_op:
        for name, type_ in missing:
            batch_op.add_column(sa.Column(name, type_, nullable=True))
            logger.info("Added %s.%s", _TABLE, name)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        return
    for name, _type in reversed(_NEW_COLUMNS):
        if not _column_exists(bind, _TABLE, name):
            continue
        try:
            with op.batch_alter_table(_TABLE) as batch_op:
                batch_op.drop_column(name)
        except Exception as e:  # broad: SQLite < 3.35 kann DROP COLUMN nicht
            logger.warning(
                "drop_column %s.%s fehlgeschlagen (SQLite < 3.35?): %s",
                _TABLE,
                name,
                e,
            )
