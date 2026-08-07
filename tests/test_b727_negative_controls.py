from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import tests.conftest as conftest_mod


REAL_DB = (Path(conftest_mod._REPO_ROOT) / "pb_studio.db").resolve()


@pytest.fixture(autouse=True)
def _restore_sqlite_connect_names():
    import sqlite3.dbapi2 as dbapi2

    saved = (sqlite3.connect, dbapi2.connect)
    yield
    sqlite3.connect, dbapi2.connect = saved


def _install_with_spy(monkeypatch):
    import sqlite3.dbapi2 as dbapi2
    from tests.support.pb_real_db_guard import install_guard

    calls: list[object] = []

    def spy(target, *args, **kwargs):
        calls.append(target)
        return object()

    monkeypatch.setattr(sqlite3, "connect", spy)
    monkeypatch.setattr(dbapi2, "connect", spy)
    install_guard([REAL_DB])
    return calls


def test_sqlite3_connect_blocks_real_db_before_original_call(monkeypatch):
    calls = _install_with_spy(monkeypatch)

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(REAL_DB)

    assert calls == []


def test_dbapi2_connect_blocks_real_db_before_original_call(monkeypatch):
    import sqlite3.dbapi2 as dbapi2

    calls = _install_with_spy(monkeypatch)

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        dbapi2.connect(str(REAL_DB))

    assert calls == []


def test_fresh_clone_repo_database_is_denied_before_it_exists():
    assert REAL_DB in conftest_mod._PROTECTED_REAL_DATABASES


def test_path_as_uri_cannot_bypass_guard(monkeypatch):
    calls = _install_with_spy(monkeypatch)

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(REAL_DB.as_uri(), uri=True)

    assert calls == []


def test_unregistered_project_database_outside_temp_is_blocked(monkeypatch):
    calls = _install_with_spy(monkeypatch)
    unknown_project_db = Path.home() / "PBStudioGuardProbe" / "pb_studio.db"

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(unknown_project_db)

    assert calls == []


def test_all_real_db_uris_blocked_including_readonly_and_substring(monkeypatch):
    calls = _install_with_spy(monkeypatch)

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(f"file:{REAL_DB}?x=mode=ro", uri=True)
    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        sqlite3.connect(f"file:{REAL_DB}?mode=ro")

    assert calls == []


def test_collection_time_real_db_access_is_blocked(tmp_path):
    attack = tmp_path / "test_collection_attack.py"
    attack.write_text(
        "import os, sqlite3\n"
        "sqlite3.connect(os.environ['PB_B727_ATTACK_DB'])\n"
        "def test_never_collected(): assert True\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PB_B727_ATTACK_DB"] = str(REAL_DB)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(attack), "--collect-only", "-q"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "TESTSCHUTZ" in output


def test_child_process_inherits_real_db_block():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sqlite3; "
                f"sqlite3.connect({str(REAL_DB)!r}); "
                "raise SystemExit('DANGER: real DB opened')"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "TESTSCHUTZ" in output
    assert "DANGER" not in output


def test_project_switch_to_repo_root_is_blocked():
    from database.session import set_project

    with pytest.raises(RuntimeError, match="TESTSCHUTZ"):
        set_project(REAL_DB.parent)


def test_temp_project_db_allowed_through_both_connect_names(monkeypatch, tmp_path):
    import sqlite3.dbapi2 as dbapi2

    calls = _install_with_spy(monkeypatch)
    temp_db = tmp_path / "pb_studio.db"

    sqlite3.connect(temp_db)
    dbapi2.connect(str(temp_db))

    assert calls == [temp_db, str(temp_db)]


def test_disabled_guard_control_proves_dangerous_access_possible(tmp_path):
    synthetic_real = tmp_path / "synthetic-real" / "pb_studio.db"
    synthetic_real.parent.mkdir()
    sqlite3.connect(synthetic_real).close()
    env = os.environ.copy()
    env["PB_STUDIO_TEST_DB_GUARD"] = "0"
    env["PB_STUDIO_TEST_REAL_DB_DENYLIST"] = json.dumps([str(synthetic_real)])

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, sqlite3; "
                "db=os.environ['PB_B727_ATTACK_DB']; "
                "c=sqlite3.connect(db); "
                "c.execute('CREATE TABLE danger(value TEXT)'); "
                "c.execute(\"INSERT INTO danger VALUES ('opened')\"); "
                "c.commit(); c.close()"
            ),
        ],
        env={**env, "PB_B727_ATTACK_DB": str(synthetic_real)},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    connection = sqlite3.connect(synthetic_real)
    try:
        assert connection.execute("SELECT value FROM danger").fetchone() == ("opened",)
    finally:
        connection.close()
