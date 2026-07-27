"""EngineProxy darf den globalen Proxy-Lock nicht ueber engine.connect() halten.

Befund (Audit 2026-07-27, Bereich db-persistenz, bestaetigt):
``EngineProxy.connect()`` rief die echte Engine INNERHALB des Proxy-RLocks.
SQLAlchemy macht dort einen eager Pool-Checkout — Pool-Wait, physischer
sqlite3.connect und der connect-Listener (PRAGMA journal_mode=WAL, busy_timeout)
laufen alle im Lock. Solange ein Thread dort steht, serialisiert der Proxy jeden
Engine-Zugriff aller anderen Threads, auch reine Attribut-Lesungen und die Reads
des Qt-Main-Threads -> mehrsekuendige GUI-Freezes.
"""

from __future__ import annotations

import threading

from database.session import EngineProxy


class _SlowEngine:
    """Engine-Attrappe, deren connect() kontrolliert haengt."""

    url = "sqlite:///fake"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.disposed = False
        self.disposed_while_connecting = False

    def connect(self, *a, **kw):
        self.started.set()
        self.release.wait(10)
        if self.disposed:
            self.disposed_while_connecting = True
        return "connection"

    def dispose(self, *a, **kw):
        self.disposed = True


def test_attribute_access_not_blocked_by_inflight_connect() -> None:
    engine = _SlowEngine()
    proxy = EngineProxy(engine)

    connector = threading.Thread(target=proxy.connect, daemon=True)
    connector.start()
    assert engine.started.wait(5), "connect() der Attrappe wurde nie erreicht"

    read_done = threading.Event()

    def _read_url() -> None:
        _ = proxy.url
        read_done.set()

    reader = threading.Thread(target=_read_url, daemon=True)
    reader.start()
    unblocked = read_done.wait(1.5)

    engine.release.set()
    connector.join(10)
    reader.join(10)

    assert unblocked, (
        "proxy.url blockierte, waehrend ein connect() noch lief — der Proxy-Lock "
        "wird weiterhin ueber den kompletten engine.connect() gehalten."
    )


def test_swap_does_not_dispose_engine_with_inflight_connect() -> None:
    """Regressions-Netz zur Lockerung oben: die Garantie 'kein dispose() waehrend
    connect()' hing frueher am gehaltenen Lock und haengt jetzt am In-Flight-
    Zaehler. Sie muss erhalten bleiben."""
    old = _SlowEngine()
    new = _SlowEngine()
    proxy = EngineProxy(old)

    connector = threading.Thread(target=proxy.connect, daemon=True)
    connector.start()
    assert old.started.wait(5)

    swap_done = threading.Event()

    def _swap() -> None:
        proxy.swap(new)
        swap_done.set()

    swapper = threading.Thread(target=_swap, daemon=True)
    swapper.start()

    # swap() muss warten, solange der connect() laeuft
    assert not swap_done.wait(0.5)
    assert old.disposed is False

    old.release.set()
    connector.join(10)
    swapper.join(10)

    assert swap_done.is_set()
    assert old.disposed is True
    assert old.disposed_while_connecting is False
