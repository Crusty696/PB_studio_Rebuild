"""Brain V3 — Phase-2-Validation-Spike: KNN-Latenz bei realen Vektor-Mengen.

Plan-Doc 06 Phase 2 DoD: "KNN-Search-Latenz median <50ms bei 16k Vektoren".
Phase-2-Tests nutzten <10 Vektoren — diese Schwelle war nicht validiert.

Dieser Spike fuellt das Repository mit N zufaelligen 512- bzw. 768-dim
Vektoren und misst KNN-Latenz median + p95 ueber 100 Queries.

Aufruf:
    python scripts/spike_brain_v3_knn_scaling.py
    python scripts/spike_brain_v3_knn_scaling.py --n-vectors 16000 --n-queries 100
    python scripts/spike_brain_v3_knn_scaling.py --skip-video

Output: outputs/spike_brain_v3_knn/<timestamp>/{snapshots.json,report.md,run.log}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_OUT_DIR = _ROOT / "outputs" / "spike_brain_v3_knn"

logger = logging.getLogger("spike_knn")


def _setup_logging(out_dir: Path) -> Path:
    log_path = out_dir / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)5s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_path


@dataclass
class ScalingResult:
    name: str
    n_vectors: int
    n_queries: int
    insert_total_s: float = 0.0
    insert_per_vector_ms: float = 0.0
    knn_latencies_ms: list[float] = field(default_factory=list)
    knn_median_ms: float = 0.0
    knn_p95_ms: float = 0.0
    knn_min_ms: float = 0.0
    knn_max_ms: float = 0.0
    plan_dod_50ms_met: bool = False
    status: str = "pending"
    error: str = ""


def benchmark(
    name: str,
    project_root: Path,
    media_type: str,
    dim: int,
    n_vectors: int,
    n_queries: int,
    add_unit_fn,
    add_emb_fn,
    knn_fn,
) -> ScalingResult:
    res = ScalingResult(name=name, n_vectors=n_vectors, n_queries=n_queries)
    try:
        # 1) Insert N Vektoren
        rng = np.random.default_rng(42)
        t0 = time.time()
        for i in range(n_vectors):
            unit = add_unit_fn(media_id=i, media_hash="0" * 64,
                               start_time=0.0, end_time=1.0)
            vec = rng.standard_normal(dim).astype("float32")
            add_emb_fn(unit.id, vec)
            if i and i % 1000 == 0:
                logger.info("  %s: inserted %d/%d", name, i, n_vectors)
        res.insert_total_s = time.time() - t0
        res.insert_per_vector_ms = res.insert_total_s * 1000 / max(1, n_vectors)
        logger.info("%s: %d vectors inserted in %.2fs (%.2f ms/vec)",
                    name, n_vectors, res.insert_total_s, res.insert_per_vector_ms)

        # 2) N_QUERIES KNN-Calls timen
        latencies_ms = []
        for q in range(n_queries):
            query = rng.standard_normal(dim).astype("float32")
            t = time.perf_counter()
            hits = knn_fn(query, k=10)
            elapsed_ms = (time.perf_counter() - t) * 1000.0
            latencies_ms.append(elapsed_ms)
            if q == 0:
                logger.info("%s: first KNN returned %d hits", name, len(hits))

        latencies_arr = np.array(latencies_ms)
        res.knn_latencies_ms = latencies_ms
        res.knn_median_ms = float(np.median(latencies_arr))
        res.knn_p95_ms = float(np.percentile(latencies_arr, 95))
        res.knn_min_ms = float(latencies_arr.min())
        res.knn_max_ms = float(latencies_arr.max())
        res.plan_dod_50ms_met = res.knn_median_ms < 50.0
        res.status = "ok"
        logger.info(
            "%s: KNN latency median=%.2fms p95=%.2fms min=%.2fms max=%.2fms — Plan-DoD <50ms: %s",
            name, res.knn_median_ms, res.knn_p95_ms, res.knn_min_ms, res.knn_max_ms,
            "MET" if res.plan_dod_50ms_met else "MISSED",
        )
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.exception("%s benchmark failed", name)
    return res


def _flush(out_dir: Path, env: dict, results: list[ScalingResult]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "environment": env,
        "results": [
            {**asdict(r),
             # Latencies-List klein halten — nur summary speichern
             "knn_latencies_ms": (r.knn_latencies_ms[:5] if r.knn_latencies_ms else [])}
            for r in results
        ],
    }
    (out_dir / "snapshots.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    md = ["# Brain V3 — Phase-2-KNN-Scaling-Spike", ""]
    md.append(f"**Generiert:** {datetime.now().isoformat()}")
    md.append("")
    md.append("## Umgebung")
    for k, v in env.items():
        md.append(f"- **{k}**: {v}")
    md.append("")
    md.append("## Ergebnisse")
    md.append("| Bench | N vectors | Insert tot. | Insert/vec | KNN median | p95 | min | max | Plan-DoD <50 ms |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        md.append(
            f"| `{r.name}` | {r.n_vectors} | {r.insert_total_s:.1f}s | "
            f"{r.insert_per_vector_ms:.2f}ms | "
            f"**{r.knn_median_ms:.2f}ms** | {r.knn_p95_ms:.2f}ms | "
            f"{r.knn_min_ms:.2f}ms | {r.knn_max_ms:.2f}ms | "
            f"{'**MET**' if r.plan_dod_50ms_met else '**MISSED**'} |"
        )
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Brain V3 KNN-Scaling-Spike")
    parser.add_argument("--n-vectors", type=int, default=16000,
                        help="Vektoren pro Bench (default 16000 = Plan-DoD-Schwelle)")
    parser.add_argument("--n-queries", type=int, default=100)
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(out_dir)

    try:
        from services.brain_v3.storage.embedding_repository import (
            EmbeddingRepository, AudioUnit, VideoUnit, CLAP_DIM, SIGLIP_DIM,
        )
    except ImportError as exc:
        logger.error("Repo-Import failed: %s", exc)
        return 2

    env = {
        "python": sys.version.split()[0],
        "n_vectors": args.n_vectors,
        "n_queries": args.n_queries,
    }
    try:
        import sqlite_vec  # type: ignore
        env["sqlite_vec"] = "installed"
    except ImportError:
        env["sqlite_vec"] = "MISSING — install via install_brain_v3_phase2_deps.bat"
        logger.error("sqlite-vec nicht installiert — Spike kann nicht laufen.")
        return 3

    project_root = out_dir / "synth_project"
    repo = EmbeddingRepository(project_root=project_root)

    results: list[ScalingResult] = []

    if not args.skip_audio:
        def add_au_unit(**kwargs):
            return repo.add_audio_unit(AudioUnit(level="window", **kwargs))
        r = benchmark(
            name=f"audio_{args.n_vectors}",
            project_root=project_root,
            media_type="audio", dim=CLAP_DIM,
            n_vectors=args.n_vectors, n_queries=args.n_queries,
            add_unit_fn=add_au_unit,
            add_emb_fn=repo.add_audio_embedding,
            knn_fn=repo.knn_audio,
        )
        results.append(r)
        _flush(out_dir, env, results)

    if not args.skip_video:
        def add_v_unit(**kwargs):
            return repo.add_video_unit(VideoUnit(level="scene", **kwargs))
        r = benchmark(
            name=f"video_{args.n_vectors}",
            project_root=project_root,
            media_type="video", dim=SIGLIP_DIM,
            n_vectors=args.n_vectors, n_queries=args.n_queries,
            add_unit_fn=add_v_unit,
            add_emb_fn=repo.add_video_embedding,
            knn_fn=repo.knn_video,
        )
        results.append(r)
        _flush(out_dir, env, results)

    logger.info("KNN-Scaling-Spike abgeschlossen.")
    print()
    print(f">>> Output: {out_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
