import database


def test_mark_cancelled_sets_retryable_status(test_engine, monkeypatch):
    from services import analysis_status_service as status_service

    monkeypatch.setattr(status_service, "nullpool_session", database.nullpool_session)

    status_service.mark_started("audio", 13, "stem_separation")
    status_service.mark_cancelled("audio", 13, "stem_separation")

    statuses = status_service.get_status("audio", 13)
    entry = statuses["stem_separation"]

    assert entry.status == "error"
    assert entry.error_message == "cancelled"

