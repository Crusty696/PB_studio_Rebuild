import datetime

from sqlalchemy.orm import Session

from database import ModelRegistry
from services.model_lifecycle_service import ModelEntry, ModelLifecycleService


def test_upsert_model_coerces_registry_datetime_fields(test_engine) -> None:
    svc = ModelLifecycleService()

    svc._upsert_model(
        ModelEntry(
            model_id="test-model",
            source="ollama",
            display_name="Test Model",
            installed_at="2026-05-13T10:11:12",
            last_used_at="",
        )
    )

    with Session(test_engine) as session:
        row = session.query(ModelRegistry).filter_by(model_id="test-model").one()
        assert isinstance(row.installed_at, datetime.datetime)
        assert row.installed_at == datetime.datetime(2026, 5, 13, 10, 11, 12)
        assert row.last_used_at is None


def test_touch_last_used_writes_datetime_to_registry(test_engine) -> None:
    with Session(test_engine) as session:
        session.add(
            ModelRegistry(
                model_id="touch-model",
                source="ollama",
                installed_at=datetime.datetime(2026, 5, 13, 9, 0, 0),
                last_used_at=None,
                status="installed",
            )
        )
        session.commit()

    svc = ModelLifecycleService()
    svc.touch_last_used("touch-model")

    with Session(test_engine) as session:
        row = session.query(ModelRegistry).filter_by(model_id="touch-model").one()
        assert isinstance(row.last_used_at, datetime.datetime)


def test_get_registry_entries_returns_iso_strings_for_datetime_columns(test_engine) -> None:
    with Session(test_engine) as session:
        session.add(
            ModelRegistry(
                model_id="read-model",
                source="huggingface",
                installed_at=datetime.datetime(2026, 5, 13, 8, 0, 0),
                last_used_at=datetime.datetime(2026, 5, 13, 9, 30, 0),
                status="installed",
            )
        )
        session.commit()

    entries = ModelLifecycleService().get_registry_entries()

    entry = next(e for e in entries if e.model_id == "read-model")
    assert entry.installed_at == "2026-05-13T08:00:00"
    assert entry.last_used_at == "2026-05-13T09:30:00"
    assert isinstance(entry.last_used_display, str)
    assert isinstance(entry.days_since_used, int)
