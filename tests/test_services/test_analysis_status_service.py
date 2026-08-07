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


def test_mark_cancelled_clears_completed_at_from_previous_done(
    test_engine,
    monkeypatch,
):
    from services import analysis_status_service as status_service

    monkeypatch.setattr(status_service, "nullpool_session", database.nullpool_session)

    status_service.mark_done("audio", 14, "av_pacing_curves", {"points": 3})
    assert status_service.get_status("audio", 14)["av_pacing_curves"].completed_at

    status_service.mark_started("audio", 14, "av_pacing_curves")
    status_service.mark_cancelled("audio", 14, "av_pacing_curves")

    entry = status_service.get_status("audio", 14)["av_pacing_curves"]
    assert entry.status == "error"
    assert entry.error_message == "cancelled"
    assert entry.completed_at is None


def test_mark_started_clears_completed_at_from_previous_done(
    test_engine,
    monkeypatch,
):
    from services import analysis_status_service as status_service

    monkeypatch.setattr(status_service, "nullpool_session", database.nullpool_session)

    status_service.mark_done("audio", 15, "onset_detection", {"onsets": 12})
    done_entry = status_service.get_status("audio", 15)["onset_detection"]
    assert done_entry.completed_at is not None

    status_service.mark_started("audio", 15, "onset_detection")

    running_entry = status_service.get_status("audio", 15)["onset_detection"]
    assert running_entry.status == "running"
    assert running_entry.error_message is None
    assert running_entry.completed_at is None
