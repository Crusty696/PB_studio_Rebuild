"""B-471 T1: viewport-lazy thumbnail scheduler — dedup + concurrency + pump."""

from __future__ import annotations

from ui.timeline_thumbnail_loader import ThumbnailLoadManager


def _mgr(max_concurrent=2):
    started: list[str] = []
    m = ThumbnailLoadManager(start_worker=started.append, max_concurrent=max_concurrent)
    return m, started


def test_request_starts_worker():
    m, started = _mgr()
    m.request("a.mp4")
    assert started == ["a.mp4"]
    assert m.inflight_count == 1


def test_request_dedups_same_path():
    m, started = _mgr()
    m.request("a.mp4")
    m.request("a.mp4")  # already inflight
    assert started == ["a.mp4"]


def test_concurrency_cap_queues_excess():
    m, started = _mgr(max_concurrent=2)
    for fp in ("a", "b", "c", "d"):
        m.request(fp)
    assert started == ["a", "b"]          # only 2 started
    assert m.inflight_count == 2
    assert m.queued_count == 2            # c, d wait


def test_on_done_pumps_next():
    m, started = _mgr(max_concurrent=2)
    for fp in ("a", "b", "c", "d"):
        m.request(fp)
    m.on_done("a")
    assert started == ["a", "b", "c"]     # c started after a finished
    m.on_done("b")
    assert started == ["a", "b", "c", "d"]
    assert m.queued_count == 0


def test_done_path_not_rerequested():
    m, started = _mgr()
    m.request("a")
    m.on_done("a")
    m.request("a")                        # already done -> skip
    assert started == ["a"]
    assert m.is_done("a")


def test_reset_clears_queue_keeps_done():
    m, started = _mgr(max_concurrent=1)
    m.request("a")
    m.request("b")                        # queued behind a
    m.on_done("a")                        # a done, b starts
    m.reset()                             # forget inflight/queue
    assert m.inflight_count == 0
    assert m.queued_count == 0
    m.request("a")                        # a already done -> not restarted
    assert started.count("a") == 1
