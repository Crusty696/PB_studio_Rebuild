"""
gui_db_inspector.py — liest die aktive SQLite-DB read-only und gibt
kompakte Snapshots als JSON aus. Wird vom pb-gui-tester Agent benutzt,
um nach jedem UI-Schritt zu verifizieren, ob DB-Seiteneffekte eintraten.

Read-only: oeffnet mit URI ?mode=ro und nutzt *keine* SQLAlchemy-Session,
damit wir auch auf eine laufende App-DB zugreifen koennen (WAL-Modus).

Kommandos:
    counts                       Zeilenzahl pro Tabelle
    latest <table> [--limit N]   Letzte N Eintraege einer Tabelle (nach id/rowid)
    tables                       Liste aller Tabellen
    snapshot                     Zeilenzahl + letzter Eintrag pro Tabelle
    query --sql "SELECT ..."     Beliebige SELECT-Query (read-only enforced)

Standard-DB: <PROJECT_ROOT>/pb_studio.db. Override via --db.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "pb_studio.db"


def _ok(**kw) -> None:
    sys.stdout.write(json.dumps({"ok": True, **kw}, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _fail(error: str, **kw) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": error, **kw}, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _open_ro(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    uri = f"file:{db.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def cmd_tables(args) -> int:
    with _open_ro(Path(args.db)) as conn:
        _ok(tables=_list_tables(conn))
    return 0


def cmd_counts(args) -> int:
    with _open_ro(Path(args.db)) as conn:
        result = {}
        for t in _list_tables(conn):
            n = conn.execute(f"SELECT COUNT(*) AS n FROM \"{t}\"").fetchone()["n"]
            result[t] = n
        _ok(counts=result)
    return 0


def _latest(conn: sqlite3.Connection, table: str, limit: int) -> list[dict]:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info(\"{table}\")").fetchall()]
    order_col = "id" if "id" in cols else "rowid"
    rows = conn.execute(
        f"SELECT * FROM \"{table}\" ORDER BY {order_col} DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def cmd_latest(args) -> int:
    with _open_ro(Path(args.db)) as conn:
        _ok(table=args.table, rows=_latest(conn, args.table, args.limit))
    return 0


def cmd_snapshot(args) -> int:
    with _open_ro(Path(args.db)) as conn:
        snap = {}
        for t in _list_tables(conn):
            n = conn.execute(f"SELECT COUNT(*) AS n FROM \"{t}\"").fetchone()["n"]
            last = _latest(conn, t, 1)
            snap[t] = {"count": n, "last": last[0] if last else None}
        _ok(snapshot=snap)
    return 0


def cmd_query(args) -> int:
    sql = args.sql.strip()
    if not sql.lower().lstrip().startswith("select"):
        _fail("only SELECT queries are allowed")
        return 2
    with _open_ro(Path(args.db)) as conn:
        rows = conn.execute(sql).fetchall()
        _ok(row_count=len(rows), rows=[dict(r) for r in rows][: args.limit])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="gui_db_inspector")
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tables").set_defaults(func=cmd_tables)
    sub.add_parser("counts").set_defaults(func=cmd_counts)
    sub.add_parser("snapshot").set_defaults(func=cmd_snapshot)

    la = sub.add_parser("latest")
    la.add_argument("table")
    la.add_argument("--limit", type=int, default=5)
    la.set_defaults(func=cmd_latest)

    qu = sub.add_parser("query")
    qu.add_argument("--sql", required=True)
    qu.add_argument("--limit", type=int, default=50)
    qu.set_defaults(func=cmd_query)

    args = p.parse_args()
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return 2
    except sqlite3.Error as exc:
        _fail(f"sqlite error: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
