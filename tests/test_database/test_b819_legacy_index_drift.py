"""B-819: Legacy-Migration darf kanonisches Head-Schema nicht veraendern."""

from sqlalchemy import create_engine, inspect

from database import migrations as migrations_mod
from database.models import Base


def _index_signatures(engine) -> set[tuple[str, str, tuple[str, ...], bool]]:
    inspector = inspect(engine)
    signatures: set[tuple[str, str, tuple[str, ...], bool]] = set()
    for table in inspector.get_table_names():
        for index in inspector.get_indexes(table):
            signatures.add(
                (
                    table,
                    str(index["name"]),
                    tuple(index["column_names"]),
                    bool(index["unique"]),
                )
            )
    return signatures


def test_b819_legacy_migrations_do_not_drift_canonical_indexes(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(migrations_mod, "engine", engine)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: engine)

    before = _index_signatures(engine)
    migrations_mod._run_legacy_migrations()
    after = _index_signatures(engine)

    assert after == before


def test_b819_intended_performance_indexes_belong_to_canonical_metadata() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    names = {signature[1] for signature in _index_signatures(engine)}

    assert {
        "idx_agent_feedback_action",
        "idx_agent_feedback_rating",
        "idx_model_registry_source",
        "idx_model_registry_last_used",
    } <= names
