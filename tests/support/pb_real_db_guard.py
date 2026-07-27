from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Iterable
from urllib.parse import unquote


GUARD_ENABLED_ENV = "PB_STUDIO_TEST_DB_GUARD"
DENYLIST_ENV = "PB_STUDIO_TEST_REAL_DB_DENYLIST"
PROTECTED_DATABASE_NAMES = {
    "pb_studio.db",
    "embeddings.db",
    "state.db",
    "weights.db",
    "patterns.db",
    "embedding_cache.db",
}


def _normalized_path(path: str | os.PathLike[str]) -> str:
    candidate = Path(path)
    return os.path.normcase(str(candidate.resolve(strict=False)))


def _normalized_target(target) -> str | None:
    try:
        raw = os.fspath(target)
    except TypeError:
        return None
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if raw == ":memory:":
        return None
    if not raw.startswith("file:"):
        return _normalized_path(raw)

    path_part = raw.removeprefix("file:").partition("?")[0]
    decoded_path = unquote(path_part)
    windows_drive_path = re.match(r"^/*([A-Za-z]:[/\\].*)$", decoded_path)
    if windows_drive_path:
        decoded_path = windows_drive_path.group(1)
    return _normalized_path(decoded_path)


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def install_guard(denied_paths: Iterable[Path | str]):
    """Patch both sqlite connect names and block protected DBs before DBAPI."""
    import sqlite3.dbapi2 as dbapi2

    denied = {_normalized_path(path) for path in denied_paths}
    allowed_temp_root = _normalized_path(tempfile.gettempdir())
    current = sqlite3.connect
    original_connect = getattr(current, "_pb_original", current)

    def guarded_connect(target, *args, **kwargs):
        normalized = _normalized_target(target)
        protected_name = (
            Path(normalized).name.casefold() if normalized is not None else ""
        )
        deny_by_policy = (
            normalized is not None
            and protected_name in PROTECTED_DATABASE_NAMES
            and not _is_under(normalized, allowed_temp_root)
        )
        if normalized in denied or deny_by_policy:
            raise RuntimeError(
                "TESTSCHUTZ (B-727): Zugriff auf geschuetzte reale DB "
                f"wurde vor sqlite3/dbapi2.connect blockiert: {target!r}"
            )
        return original_connect(target, *args, **kwargs)

    guarded_connect._pb_original = original_connect
    guarded_connect._pb_denied = frozenset(denied)
    sqlite3.connect = guarded_connect
    dbapi2.connect = guarded_connect
    return guarded_connect


def configure_child_environment(
    denied_paths: Iterable[Path | str],
    *,
    support_root: Path,
) -> None:
    denied = [_normalized_path(path) for path in denied_paths]
    os.environ[GUARD_ENABLED_ENV] = "1"
    os.environ[DENYLIST_ENV] = json.dumps(denied)
    current = os.environ.get("PYTHONPATH", "")
    entries = [entry for entry in current.split(os.pathsep) if entry]
    support_text = str(support_root.resolve())
    if os.path.normcase(support_text) not in {
        os.path.normcase(entry) for entry in entries
    }:
        entries.insert(0, support_text)
    os.environ["PYTHONPATH"] = os.pathsep.join(entries)


def install_from_environment() -> bool:
    if os.environ.get(GUARD_ENABLED_ENV) != "1":
        return False
    raw = os.environ.get(DENYLIST_ENV, "[]")
    denied = json.loads(raw)
    if not isinstance(denied, list):
        raise RuntimeError(f"{DENYLIST_ENV} must contain a JSON list")
    install_guard(denied)
    return True
