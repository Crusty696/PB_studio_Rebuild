"""B-727: Der sqlite3-connect-Guard muss den Zugriff WIRKLICH verhindern.

Defekt (gefunden 2026-07-27): ``_guarded_connect(database, ...)`` benannte
seinen ersten Parameter ``database`` und ueberdeckte damit das oben
importierte Projektmodul gleichen Namens. Im Fehlertext stand
``database.engine`` — ausgewertet wurde das auf dem uebergebenen Pfad-String,
nicht auf dem Modul. Ergebnis: ``AttributeError`` statt ``RuntimeError``,
verschluckt vom breiten ``except Exception: pass`` — und danach lief
``original_connect()`` ganz normal weiter.

Der Guard meldete also Schutz, ohne zu schuetzen. Diese Tests sichern beide
Eigenschaften ab: es fliegt ein RuntimeError, UND die echte Verbindung wird
gar nicht erst aufgebaut.
"""
from __future__ import annotations

import sqlite3

import pytest

import tests.conftest as conftest_mod


REAL_DB = next(
    path
    for path in conftest_mod._PROTECTED_REAL_DATABASES
    if path.name == "pb_studio.db" and path.is_file()
)


@pytest.fixture(autouse=True)
def _restore_connect_hooks():
    """Beide connect-Namen nach jedem Test zuruecksetzen.

    Die Tests hier installieren den Guard absichtlich neu, waehrend
    ``sqlite3.connect`` per monkeypatch durch einen Spy ersetzt ist. Der
    Guard schreibt sich dabei auch nach ``sqlite3.dbapi2.connect`` — und
    monkeypatch kennt diesen zweiten Namen nicht. Ohne Restore bleibt dort
    ein Guard stehen, der einen laengst entfernten Spy als Original haelt;
    SQLAlchemy (das ueber ``dbapi2`` geht) faellt danach mit AttributeError.
    """
    import sqlite3
    import sqlite3.dbapi2 as dbapi2

    saved = (sqlite3.connect, dbapi2.connect)
    yield
    sqlite3.connect, dbapi2.connect = saved


def test_guard_raises_and_never_opens_the_real_database(monkeypatch):
    """Kernbeweis: RuntimeError UND null Durchgriffe auf original_connect."""
    calls: list[object] = []

    def _spy_connect(target, *args, **kwargs):
        calls.append(target)
        raise AssertionError(
            "original_connect wurde trotz Guard aufgerufen — die reale DB "
            f"waere geoeffnet worden ({target!r})."
        )

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    conftest_mod._install_real_db_connect_guard()

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(str(REAL_DB))

    assert calls == [], "Der Guard hat den Zugriff durchgelassen."


def test_guard_message_survives_broken_engine(monkeypatch):
    """Auch wenn die Diagnose-Angabe scheitert, muss geblockt werden.

    Frueher kippte genau daran die ganze Blockade: die Meldung wollte
    ``engine.url`` lesen, das warf, und der Zugriff lief durch.
    """
    import database

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("Engine kaputt")

    monkeypatch.setattr(database, "engine", _Boom(), raising=False)
    monkeypatch.setattr(
        sqlite3, "connect",
        lambda *a, **k: pytest.fail("reale DB wurde geoeffnet"),
    )
    conftest_mod._install_real_db_connect_guard()

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(str(REAL_DB))


def test_readonly_uri_to_real_database_is_blocked(monkeypatch):
    """Auch Diagnose-Reads muessen gegen RAW-Kopien statt Originale laufen."""
    seen: list[str] = []
    monkeypatch.setattr(
        sqlite3, "connect",
        lambda target, *a, **k: seen.append(str(target)) or object(),
    )
    conftest_mod._install_real_db_connect_guard()

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    assert seen == []


def test_temp_database_stays_allowed(monkeypatch, tmp_path):
    """Die Temp-DB heisst auch pb_studio.db und darf NICHT blockiert werden."""
    seen: list[str] = []
    monkeypatch.setattr(
        sqlite3, "connect",
        lambda target, *a, **k: seen.append(str(target)) or object(),
    )
    conftest_mod._install_real_db_connect_guard()

    sqlite3.connect(str(tmp_path / "pb_studio.db"))
    assert len(seen) == 1
