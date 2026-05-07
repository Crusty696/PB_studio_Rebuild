"""Phase 6 R18 KNN ANN eval for sqlite-vec.

This checks whether the installed sqlite-vec exposes an ANN/HNSW module before
any schema migration is considered. If no ANN module is present, keeping vec0
and the relaxed <150 ms p95 DoD is the only honest result.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


ANN_MARKERS = ("hnsw", "ann", "ivf")


def detect_ann_support(vec_version: str, module_names: list[str]) -> dict[str, Any]:
    ann_modules = [
        name for name in module_names
        if any(marker in name.lower() for marker in ANN_MARKERS)
    ]
    return {
        "vec_version": vec_version,
        "modules": sorted(module_names),
        "ann_modules": sorted(ann_modules),
        "ann_module_available": bool(ann_modules),
        "status": "ready" if ann_modules else "blocked-no-ann-module",
    }


def _connect_vec() -> sqlite3.Connection:
    import sqlite_vec  # type: ignore

    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _vec_blob(values: np.ndarray) -> bytes:
    return values.astype(np.float32).tobytes(order="C")


def collect_sqlite_vec_capabilities() -> dict[str, Any]:
    with _connect_vec() as conn:
        vec_version = str(conn.execute("select vec_version()").fetchone()[0])
        modules = [str(row[0]) for row in conn.execute("pragma module_list").fetchall()]
    return detect_ann_support(vec_version=vec_version, module_names=modules)


def detect_vectorlite_support() -> dict[str, Any]:
    available = (
        importlib.util.find_spec("vectorlite_py") is not None
        and importlib.util.find_spec("apsw") is not None
    )
    return {
        "available": available,
        "packages": {
            "vectorlite_py": importlib.util.find_spec("vectorlite_py") is not None,
            "apsw": importlib.util.find_spec("apsw") is not None,
        },
    }


def run_vec0_smoke(n_vectors: int = 512, dim: int = 64, n_queries: int = 5) -> dict[str, Any]:
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(n_vectors, dim)).astype(np.float32)
    queries = rng.normal(size=(n_queries, dim)).astype(np.float32)
    insert_start = time.perf_counter()
    query_ms: list[float] = []
    with _connect_vec() as conn:
        conn.execute(f"create virtual table vec_eval using vec0(embedding float[{dim}])")
        conn.executemany(
            "insert into vec_eval(rowid, embedding) values (?, ?)",
            [(idx + 1, _vec_blob(vec)) for idx, vec in enumerate(vectors)],
        )
        conn.commit()
        insert_ms = (time.perf_counter() - insert_start) * 1000.0

        for query in queries:
            start = time.perf_counter()
            rows = conn.execute(
                "select rowid, distance from vec_eval "
                "where embedding match ? and k = ? "
                "order by distance",
                (_vec_blob(query), 10),
            ).fetchall()
            query_ms.append((time.perf_counter() - start) * 1000.0)
            if not rows:
                raise RuntimeError("vec0 KNN returned no rows")

    return {
        "inserted": n_vectors,
        "dim": dim,
        "queries": n_queries,
        "insert_ms": insert_ms,
        "query_ms": {
            "min": min(query_ms),
            "median": float(np.percentile(query_ms, 50)),
            "p95": float(np.percentile(query_ms, 95)),
            "max": max(query_ms),
        },
    }


def run_vectorlite_smoke(
    n_vectors: int = 512,
    dim: int = 64,
    n_queries: int = 5,
) -> dict[str, Any]:
    support = detect_vectorlite_support()
    if not support["available"]:
        return {"status": "skipped", "support": support}

    import apsw  # type: ignore
    import vectorlite_py  # type: ignore

    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(n_vectors, dim)).astype(np.float32)
    queries = rng.normal(size=(n_queries, dim)).astype(np.float32)
    query_ms: list[float] = []
    insert_start = time.perf_counter()
    conn = apsw.Connection(":memory:")
    try:
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())
        cur = conn.cursor()
        info = cur.execute("select vectorlite_info()").fetchall()
        cur.execute(
            f"create virtual table ann_eval using vectorlite("
            f"embedding float32[{dim}], hnsw(max_elements={n_vectors}))"
        )
        cur.executemany(
            "insert into ann_eval(rowid, embedding) values (?, ?)",
            [(idx + 1, vectors[idx].tobytes()) for idx in range(n_vectors)],
        )
        insert_ms = (time.perf_counter() - insert_start) * 1000.0
        for query in queries:
            start = time.perf_counter()
            rows = cur.execute(
                "select rowid, distance from ann_eval "
                "where knn_search(embedding, knn_param(?, 10))",
                [query.tobytes()],
            ).fetchall()
            query_ms.append((time.perf_counter() - start) * 1000.0)
            if not rows:
                raise RuntimeError("vectorlite KNN returned no rows")
    finally:
        conn.close()

    return {
        "status": "ok",
        "support": support,
        "info": info,
        "inserted": n_vectors,
        "dim": dim,
        "queries": n_queries,
        "insert_ms": insert_ms,
        "query_ms": {
            "min": min(query_ms),
            "median": float(np.percentile(query_ms, 50)),
            "p95": float(np.percentile(query_ms, 95)),
            "max": max(query_ms),
        },
    }


def run(
    out_root: Path,
    n_vectors: int = 512,
    dim: int = 64,
    n_queries: int = 5,
) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    capabilities = collect_sqlite_vec_capabilities()
    vec0_smoke = run_vec0_smoke(n_vectors=n_vectors, dim=dim, n_queries=n_queries)
    vectorlite_smoke = run_vectorlite_smoke(
        n_vectors=n_vectors,
        dim=dim,
        n_queries=n_queries,
    )
    status = capabilities["status"]
    if status == "blocked-no-ann-module" and vectorlite_smoke["status"] == "ok":
        status = "ready-external-vectorlite"
    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "out_dir": str(out_dir),
        "out_dir_name": stamp,
        "status": status,
        "capabilities": capabilities,
        "vec0_smoke": vec0_smoke,
        "vectorlite_smoke": vectorlite_smoke,
        "decision": (
            "Do not add ANN/HNSW migration; installed sqlite-vec exposes no ANN module."
            if status == "blocked-no-ann-module"
            else "External vectorlite HNSW is available; keep separate until a plan decision approves production integration."
            if status == "ready-external-vectorlite"
            else "ANN module visible; create separate migration spike before production use."
        ),
    }
    (out_dir / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-root",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "spike_brain_v3_knn_ann_eval",
    )
    parser.add_argument("--n-vectors", type=int, default=512)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--n-queries", type=int, default=5)
    args = parser.parse_args()
    result = run(
        args.out_root,
        n_vectors=args.n_vectors,
        dim=args.dim,
        n_queries=args.n_queries,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
