"""B-678: Brain-V3-Storage muss seine sqlite3-Connections schliessen.

``with self._conn() as conn:`` auf einer rohen Connection committet nur,
schliesst aber nie -> Handle-Leck pro Aufruf (+ WAL/SHM). Die Tests fangen jede
via ``open_connection`` geoeffnete Connection ab und pruefen, dass sie nach der
Storage-Operation geschlossen ist (execute auf geschlossener Connection wirft
``sqlite3.ProgrammingError``).
"""

import sqlite3

import pytest


def _tracking(monkeypatch, module):
    """Patcht ``module.open_connection`` so, dass alle geoeffneten Connections
    gesammelt werden. Gibt die Liste zurueck."""
    opened = []
    real = module.open_connection

    def _open(path):
        conn = real(path)
        opened.append(conn)
        return conn

    monkeypatch.setattr(module, "open_connection", _open)
    return opened


def _assert_all_closed(opened):
    assert opened, "keine Connection geoeffnet — Test greift nicht"
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_embedding_cache_closes_connection(tmp_path, monkeypatch):
    from services.brain.storage import embedding_cache as mod

    cache = mod.EmbeddingCache(db_path=tmp_path / "ec.db")  # Konstruktion vor Tracking
    opened = _tracking(monkeypatch, mod)

    cache.stats()  # nutzt _conn

    _assert_all_closed(opened)


def test_media_hash_registry_closes_connection(tmp_path, monkeypatch):
    from services.brain.storage import media_hash_registry as mod

    reg = mod.MediaHashRegistry(db_path=tmp_path / "mh.db")
    opened = _tracking(monkeypatch, mod)

    reg.stats()  # nutzt _conn

    _assert_all_closed(opened)


def test_brain_store_closes_connections(tmp_path, monkeypatch):
    from services.brain.storage import brain_store as mod

    store = mod.BrainStore(
        weights_path=tmp_path / "w.db",
        patterns_path=tmp_path / "p.db",
    )
    opened = _tracking(monkeypatch, mod)

    store.stats()  # open_weights + open_patterns (+ ggf. ec)

    _assert_all_closed(opened)
