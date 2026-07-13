from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace


class _FakeNullPoolEngine:
    def __init__(self, url: str):
        self.url = url
        self.dispose_calls = 0

    def dispose(self):
        self.dispose_calls += 1


def _clear_cache(monkeypatch, session_module) -> None:
    monkeypatch.setattr(session_module, "_nullpool_engine_cache", None)


def test_nullpool_session_reuses_one_engine_for_same_url(monkeypatch):
    import database.session as session_module

    _clear_cache(monkeypatch, session_module)
    monkeypatch.setattr(
        session_module, "engine", SimpleNamespace(url="sqlite:///project-a.db")
    )
    created = []

    def fake_factory(url, *, enable_foreign_keys):
        created.append((url, enable_foreign_keys))
        return _FakeNullPoolEngine(url)

    monkeypatch.setattr(session_module, "make_nullpool_engine", fake_factory)

    first = session_module.nullpool_session()
    second = session_module.nullpool_session()

    assert first._eng is second._eng
    assert created == [("sqlite:///project-a.db", True)]
    assert first._dispose_engine is False


def test_nullpool_cache_switches_url_without_disrupting_previous_engine(monkeypatch):
    import database.session as session_module

    _clear_cache(monkeypatch, session_module)
    current = SimpleNamespace(url="sqlite:///project-a.db")
    monkeypatch.setattr(session_module, "engine", current)
    made = []

    def fake_factory(url, *, enable_foreign_keys):
        result = _FakeNullPoolEngine(url)
        made.append(result)
        return result

    monkeypatch.setattr(session_module, "make_nullpool_engine", fake_factory)
    old_context = session_module.nullpool_session()
    current.url = "sqlite:///project-b.db"
    new_context = session_module.nullpool_session()

    assert new_context._eng is not old_context._eng
    assert [item.url for item in made] == [
        "sqlite:///project-a.db",
        "sqlite:///project-b.db",
    ]
    assert made[0].dispose_calls == 0
    assert made[1].dispose_calls == 0


def test_nullpool_cache_factory_is_single_flight_across_threads(monkeypatch):
    import database.session as session_module

    _clear_cache(monkeypatch, session_module)
    monkeypatch.setattr(
        session_module, "engine", SimpleNamespace(url="sqlite:///threaded.db")
    )
    made = []

    def fake_factory(url, *, enable_foreign_keys):
        result = _FakeNullPoolEngine(url)
        made.append(result)
        return result

    monkeypatch.setattr(session_module, "make_nullpool_engine", fake_factory)
    with ThreadPoolExecutor(max_workers=8) as pool:
        engines = list(pool.map(lambda _index: session_module.nullpool_session()._eng, range(64)))

    assert len(made) == 1
    assert all(item is made[0] for item in engines)


def test_cached_nullpool_engine_still_opens_fresh_connections(monkeypatch, tmp_path):
    import database.session as session_module

    _clear_cache(monkeypatch, session_module)
    db_path = tmp_path / "fresh-connections.db"
    monkeypatch.setattr(
        session_module, "engine", SimpleNamespace(url=f"sqlite:///{db_path}")
    )
    first = session_module.nullpool_session()
    second = session_module.nullpool_session()

    with first as first_session, second as second_session:
        first_dbapi = first_session.connection().connection.driver_connection
        second_dbapi = second_session.connection().connection.driver_connection
        assert first._eng is second._eng
        assert first_dbapi is not second_dbapi

    first._eng.dispose()


def test_set_project_url_drives_next_nullpool_engine(monkeypatch, tmp_path):
    import database.models as models
    import database.session as session_module

    _clear_cache(monkeypatch, session_module)
    monkeypatch.setattr(session_module, "APP_ROOT", session_module.APP_ROOT)
    initial = _FakeNullPoolEngine("sqlite:///old-project.db")
    monkeypatch.setattr(session_module, "engine", session_module.EngineProxy(initial))
    monkeypatch.setattr(session_module, "_running_tasks_block_reason", lambda **_kw: None)
    monkeypatch.setattr(session_module, "_patch_service_paths", lambda _path: None)
    monkeypatch.setattr(models.Base.metadata, "create_all", lambda _engine: None)
    monkeypatch.setattr(
        session_module,
        "_make_engine",
        lambda db_path: _FakeNullPoolEngine(f"sqlite:///{db_path}"),
    )
    captured = []

    def fake_factory(url, *, enable_foreign_keys):
        captured.append(url)
        return _FakeNullPoolEngine(url)

    monkeypatch.setattr(session_module, "make_nullpool_engine", fake_factory)
    project = tmp_path / "project-b"

    session_module.set_project(project)
    context = session_module.nullpool_session()

    assert captured == [f"sqlite:///{project / 'pb_studio.db'}"]
    assert context._eng.url.endswith("project-b\\pb_studio.db") or context._eng.url.endswith(
        "project-b/pb_studio.db"
    )
