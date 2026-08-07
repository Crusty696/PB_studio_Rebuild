"""B-764 — EngineProxy-Identitaetsvertrag gegenueber SQLAlchemy-Session-Binds.

Root Cause: ``SessionTransaction._connection_for_bind`` (sqlalchemy 2.0.51,
``orm/session.py`` ab Z. 1154) cached offene Verbindungen in einem Dict unter
``conn.engine`` (= ECHTE innere Engine), sucht aber mit dem Session-bind
(``EngineProxy``) als Key: ``if bind in self._connections``. Der Dict-Lookup
vergleicht ``stored_key.__eq__(proxy)`` -> ``NotImplemented`` (Engine hat kein
eigenes ``__eq__``) -> reflektiert ``proxy.__eq__(stored_key)``. Ohne
``__hash__``/``__eq__``-Delegation am Proxy traf der Lookup nie ->
jeder Write-Batch zog eine ZWEITE Pool-Verbindung -> SQLite-Self-Deadlock
("database is locked" nach busy_timeout 120s).
"""

import pytest
from sqlalchemy import Column, Integer, String, create_engine, event
from sqlalchemy.orm import Session, declarative_base

from database import engine as global_engine_proxy
from database.session import EngineProxy, get_raw_engine


class TestIdentityContract:
    """Kernvertrag ohne DB-Zugriff — exakt die Dict-Semantik von SQLAlchemy."""

    def test_hash_matches_inner_engine(self):
        inner = get_raw_engine()
        assert hash(global_engine_proxy) == hash(inner)

    def test_proxy_eq_inner_engine_both_directions(self):
        inner = get_raw_engine()
        # Richtung Proxy == Engine (Proxy.__eq__ direkt)
        assert global_engine_proxy == inner
        # Richtung Engine == Proxy: Engine.__eq__ -> NotImplemented ->
        # Python reflektiert auf Proxy.__eq__ -> True. Genau diese Richtung
        # nutzt der CPython-Dict-Lookup (stored_key == lookup_key).
        assert inner == global_engine_proxy

    def test_proxy_found_in_dict_keyed_by_inner_engine(self):
        # Exakte SessionTransaction-Semantik: Dict-Key = echte Engine
        # (Z. 1254: self._connections[conn.engine] = ...), Lookup mit dem
        # Proxy als bind (Z. 1162: if bind in self._connections).
        inner = get_raw_engine()
        assert global_engine_proxy in {inner: "conn"}

    def test_proxy_eq_self_and_other_proxy_same_engine(self):
        inner = get_raw_engine()
        assert global_engine_proxy == global_engine_proxy
        assert global_engine_proxy == EngineProxy(inner)

    def test_proxy_not_eq_unrelated(self):
        assert not (global_engine_proxy == object())


# ---------------------------------------------------------------------------
# Verhaltensvertrag: eigene tmp-Engine + Proxy, KEINE globale conftest-Engine.
# ---------------------------------------------------------------------------

_Base = declarative_base()


class _B764A(_Base):
    __tablename__ = "b764_a"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class _B764B(_Base):
    __tablename__ = "b764_b"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class TestSingleConnectionPerTransaction:
    def test_two_write_batches_one_connection_no_lock(self, tmp_path):
        """Zwei flush-Batches in EINER Transaktion muessen auf EINER
        Pool-Verbindung laufen. Vor Fix: 2 Checkouts + OperationalError
        'database is locked' (Self-Deadlock)."""
        real = create_engine(
            f"sqlite:///{tmp_path / 'b764.db'}",
            connect_args={"check_same_thread": False, "timeout": 0.5},
        )
        _Base.metadata.create_all(real)

        checkout_ids = []

        @event.listens_for(real.pool, "checkout")
        def _on_checkout(dbapi_conn, connection_record, connection_proxy):
            checkout_ids.append(id(dbapi_conn))

        proxy = EngineProxy(real)
        try:
            with Session(proxy) as s:
                s.add(_B764A(name="erster Write-Batch"))
                s.flush()
                s.add(_B764B(name="zweiter Write-Batch"))
                s.flush()  # vor Fix: zweite Pool-Verbindung -> database is locked
                s.commit()
        finally:
            proxy.dispose()

        assert len(checkout_ids) == 1, (
            f"Erwartet genau 1 Pool-Checkout pro Session-Transaktion, "
            f"waren {len(checkout_ids)}: {checkout_ids}"
        )
