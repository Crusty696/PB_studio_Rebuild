from __future__ import annotations

import threading


def test_convert_db_pool_shutdown_stops_worker_thread():
    from ui.controllers import convert

    event = threading.Event()
    convert.submit_convert_db_job(lambda: event.set()).result(timeout=2)
    assert event.is_set()
    assert any(t.name.startswith("convert_db") for t in threading.enumerate())

    assert convert.shutdown_convert_db_pool(timeout=2.0)

    assert not any(t.name.startswith("convert_db") for t in threading.enumerate())


def test_convert_db_pool_restarts_after_shutdown():
    from ui.controllers import convert

    assert convert.shutdown_convert_db_pool(timeout=2.0)

    event = threading.Event()
    convert.submit_convert_db_job(lambda: event.set()).result(timeout=2)

    try:
        assert event.is_set()
        assert any(t.name.startswith("convert_db") for t in threading.enumerate())
    finally:
        convert.shutdown_convert_db_pool(timeout=2.0)
