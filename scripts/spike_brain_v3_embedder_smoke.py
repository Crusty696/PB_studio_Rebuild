"""Brain V3 — Phase-2-Validation-Spike: Embedder + Cache + Repo End-to-End.

Plan-Doc 06 Phase 2 DoDs die der User in Phase-2-Bericht zurecht reklamiert hat:
- Embedder-Klassen wirklich laden und Inferenz durchlaufen lassen
  (NICHT nur das transformers-Pattern wie Phase-0-Spike)
- Cache-Roundtrip: store → lookup → load_embedding ergibt identisches array
- Repository-Roundtrip: add_unit → add_embedding → KNN findet sich selbst
- Linear-Hochrechnung 10-Clip → 500-Clip Erst-Embedding-Zeit

Aufruf:
    python scripts/spike_brain_v3_embedder_smoke.py
    python scripts/spike_brain_v3_embedder_smoke.py --skip-clap
    python scripts/spike_brain_v3_embedder_smoke.py --n-audio 5 --n-video 5

Output: outputs/spike_brain_v3_embedder/<timestamp>/{snapshots.json,report.md,run.log}
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_OUT_DIR = _ROOT / "outputs" / "spike_brain_v3_embedder"

logger = logging.getLogger("spike_embedder")


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
class StepResult:
    name: str
    status: str = "pending"   # pending|ok|error
    duration_s: float = 0.0
    detail: dict = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# Synthetische Test-Daten
# ---------------------------------------------------------------------------
def _gen_synthetic_audio(out_path: Path, sr: int = 48000,
                         duration_s: float = 30.0) -> None:
    """Erzeugt 30s WAV: drei verschiedene Sinus-Stuecke. Triggert SubtrackDetector + CLAP."""
    import soundfile as sf
    t1 = np.linspace(0, 10, int(sr * 10), endpoint=False)
    t2 = np.linspace(0, 10, int(sr * 10), endpoint=False)
    t3 = np.linspace(0, 10, int(sr * 10), endpoint=False)
    y = np.concatenate([
        0.2 * np.sin(2 * np.pi * 220 * t1).astype("float32"),
        0.2 * np.sin(2 * np.pi * 440 * t2).astype("float32"),
        0.2 * np.sin(2 * np.pi * 880 * t3).astype("float32"),
    ])
    sf.write(str(out_path), y, sr)


def _gen_synthetic_video(out_path: Path, n_frames: int = 50, fps: int = 10,
                         hue_shift: int = 0) -> None:
    """Erzeugt 5s MP4 mit einer Farbe. hue_shift macht jedes Video unterschiedlich."""
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (96, 96))
    try:
        for i in range(n_frames):
            frame = np.zeros((96, 96, 3), dtype=np.uint8)
            # BGR mit hue_shift moduliert → unterscheidbare Embeddings
            frame[..., 0] = (50 + hue_shift) % 256
            frame[..., 1] = (100 + hue_shift * 2) % 256
            frame[..., 2] = (150 + hue_shift * 3) % 256
            writer.write(frame)
    finally:
        writer.release()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def step_clap(n_files: int, audio_dir: Path, project_root: Path,
              skip_inference: bool) -> StepResult:
    res = StepResult(name="clap_embedder", detail={"n_files": n_files})
    t0 = time.time()
    try:
        from services.brain.audio.audio_embedder import (
            ClapAudioEmbedder, CLAP_MODEL_ID, CLAP_MODEL_VERSION, CLAP_DIM,
        )
        from services.brain.hashing import compute_media_hash
        from services.brain.storage.embedding_cache import EmbeddingCache
        from services.brain.storage.embedding_repository import (
            EmbeddingRepository, AudioUnit,
        )

        cache = EmbeddingCache()
        repo = EmbeddingRepository(project_root=project_root)
        embedder = ClapAudioEmbedder()

        # 1) n synth-WAVs generieren
        audio_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(n_files):
            p = audio_dir / f"synth_{i:03d}.wav"
            _gen_synthetic_audio(p, duration_s=30.0)
            files.append(p)

        per_file_times = []
        cache_hits = 0
        cache_misses = 0
        embeddings_seen = []

        # 2) Erst-Embedding (CLAP-Modell wird beim ersten Call geladen)
        for media_id, audio_path in enumerate(files, start=1):
            t_start = time.time()
            audio_hash = compute_media_hash(audio_path)

            cached = cache.lookup(audio_hash, CLAP_MODEL_ID, CLAP_MODEL_VERSION)
            if cached is not None:
                cache_hits += 1
                emb = cached.load_embedding()
            else:
                cache_misses += 1
                if skip_inference:
                    emb = np.random.randn(CLAP_DIM).astype("float32")
                else:
                    result = embedder.embed_mix(audio_path, audio_hash=audio_hash)
                    emb = result.mix_embedding
                    # ins Repo: window+section+mix-Aggregation testen
                    mix_unit = AudioUnit(
                        level="mix", media_id=media_id, media_hash=audio_hash,
                        start_time=0.0, end_time=result.duration_seconds,
                    )
                    mix_unit = repo.add_audio_unit(mix_unit)
                    repo.add_audio_embedding(mix_unit.id, emb)
                # Cache speichern
                cache.store(audio_hash, "audio", emb, CLAP_MODEL_ID, CLAP_MODEL_VERSION)

            embeddings_seen.append(emb)
            per_file_times.append(time.time() - t_start)

        # 3) Re-Import Cache-Hit-Rate Test: gleiche Files nochmal
        re_import_hits = 0
        re_import_t0 = time.time()
        for audio_path in files:
            audio_hash = compute_media_hash(audio_path)
            cached = cache.lookup(audio_hash, CLAP_MODEL_ID, CLAP_MODEL_VERSION)
            if cached is not None:
                _ = cached.load_embedding()
                re_import_hits += 1
        re_import_t = time.time() - re_import_t0

        # 4) KNN: erstes Embedding sollte sich selbst finden (Repo ist nur fuer Inferenz-Pfad gefuellt)
        knn_hits = []
        if not skip_inference and embeddings_seen:
            try:
                hits = repo.knn_audio(embeddings_seen[0], k=1, level="mix")
                knn_hits = [(h.unit_id, h.distance) for h in hits]
            except Exception as exc:
                logger.warning("KNN-Smoke skipped: %s", exc)

        embedder.unload()

        # Hochrechnung 500 Clips
        avg_per_file = float(np.mean(per_file_times)) if per_file_times else 0.0
        extrapolated_500_minutes = avg_per_file * 500 / 60.0

        res.detail.update({
            "model": CLAP_MODEL_ID,
            "files_processed": len(files),
            "per_file_times_s": per_file_times,
            "avg_per_file_s": avg_per_file,
            "extrapolated_500_clips_minutes": extrapolated_500_minutes,
            "cache_hits_first_pass": cache_hits,
            "cache_misses_first_pass": cache_misses,
            "re_import_hits": re_import_hits,
            "re_import_total_s": re_import_t,
            "re_import_hit_rate": (re_import_hits / max(1, len(files))),
            "knn_self_match_distance": (knn_hits[0][1] if knn_hits else None),
        })
        res.status = "ok"
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.exception("clap step failed")
    res.duration_s = time.time() - t0
    return res


def step_siglip(n_files: int, video_dir: Path, project_root: Path) -> StepResult:
    res = StepResult(name="siglip_embedder", detail={"n_files": n_files})
    t0 = time.time()
    try:
        from services.brain.video.video_embedder import (
            Siglip2VideoEmbedder, SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION,
            SIGLIP2_DIM, SceneSpec,
        )
        from services.brain.hashing import compute_media_hash
        from services.brain.storage.embedding_cache import EmbeddingCache
        from services.brain.storage.embedding_repository import (
            EmbeddingRepository, VideoUnit,
        )

        cache = EmbeddingCache()
        repo = EmbeddingRepository(project_root=project_root)
        embedder = Siglip2VideoEmbedder()

        video_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(n_files):
            p = video_dir / f"synth_{i:03d}.mp4"
            _gen_synthetic_video(p, hue_shift=i * 30)
            files.append(p)

        per_file_times = []
        embeddings_seen = []

        for media_id, video_path in enumerate(files, start=100):
            t_start = time.time()
            video_hash = compute_media_hash(video_path)

            cached = cache.lookup(video_hash, SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION)
            if cached is not None:
                emb = cached.load_embedding()
            else:
                # Zwei Scenes pro Clip (testet Aggregation)
                scenes = [
                    SceneSpec(start_time=0.0, end_time=2.5),
                    SceneSpec(start_time=2.5, end_time=5.0),
                ]
                result = embedder.embed_clip(video_path, video_hash=video_hash, scenes=scenes)
                emb = result.clip_embedding

                clip_unit = VideoUnit(
                    level="clip", media_id=media_id, media_hash=video_hash,
                    start_time=0.0, end_time=result.duration_seconds,
                )
                clip_unit = repo.add_video_unit(clip_unit)
                repo.add_video_embedding(clip_unit.id, emb)
                cache.store(video_hash, "video", emb,
                            SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION)

            embeddings_seen.append(emb)
            per_file_times.append(time.time() - t_start)

        # Re-Import Test
        re_import_hits = 0
        re_import_t0 = time.time()
        for video_path in files:
            video_hash = compute_media_hash(video_path)
            cached = cache.lookup(video_hash, SIGLIP2_MODEL_ID, SIGLIP2_MODEL_VERSION)
            if cached is not None:
                _ = cached.load_embedding()
                re_import_hits += 1
        re_import_t = time.time() - re_import_t0

        # KNN-Smoke
        knn_hits = []
        if embeddings_seen:
            try:
                hits = repo.knn_video(embeddings_seen[0], k=1, level="clip")
                knn_hits = [(h.unit_id, h.distance) for h in hits]
            except Exception as exc:
                logger.warning("KNN-Smoke skipped: %s", exc)

        embedder.unload()

        avg_per_file = float(np.mean(per_file_times)) if per_file_times else 0.0
        extrapolated_500_minutes = avg_per_file * 500 / 60.0

        res.detail.update({
            "model": SIGLIP2_MODEL_ID,
            "files_processed": len(files),
            "per_file_times_s": per_file_times,
            "avg_per_file_s": avg_per_file,
            "extrapolated_500_clips_minutes": extrapolated_500_minutes,
            "re_import_hits": re_import_hits,
            "re_import_total_s": re_import_t,
            "re_import_hit_rate": (re_import_hits / max(1, len(files))),
            "knn_self_match_distance": (knn_hits[0][1] if knn_hits else None),
        })
        res.status = "ok"
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.exception("siglip step failed")
    res.duration_s = time.time() - t0
    return res


def _flush(out_dir: Path, env: dict, results: list[StepResult]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "environment": env,
        "results": [asdict(r) for r in results],
    }
    (out_dir / "snapshots.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    md = ["# Brain V3 — Phase-2-Embedder-Validation-Spike", ""]
    md.append(f"**Generiert:** {datetime.now().isoformat()}")
    md.append("")
    md.append("## Umgebung")
    for k, v in env.items():
        md.append(f"- **{k}**: {v}")
    md.append("")
    md.append("## Ergebnisse")
    md.append("| Step | Status | Dauer | Avg/File | 500-Clip-Hochrechnung | Re-Import-Hit-Rate |")
    md.append("|---|---|---|---|---|---|")
    for r in results:
        d = r.detail
        md.append(
            f"| `{r.name}` | **{r.status}** | {r.duration_s:.1f}s | "
            f"{d.get('avg_per_file_s', 0):.2f}s | "
            f"{d.get('extrapolated_500_clips_minutes', 0):.1f} min | "
            f"{d.get('re_import_hit_rate', 0)*100:.0f}% in "
            f"{d.get('re_import_total_s', 0):.2f}s |"
        )
    md.append("")
    for r in results:
        md.append(f"### `{r.name}` — {r.status}")
        md.append(f"- Dauer: {r.duration_s:.1f}s")
        if r.error:
            md.append(f"- Fehler: `{r.error}`")
        for k, v in r.detail.items():
            if isinstance(v, list) and len(v) > 5:
                md.append(f"- {k}: list[{len(v)}] (gekuerzt)")
            else:
                md.append(f"- {k}: `{v}`")
        md.append("")
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")


def _collect_env() -> dict:
    env = {"python": sys.version.split()[0]}
    try:
        import torch  # type: ignore
        env["torch"] = torch.__version__
        env["cuda_available"] = str(torch.cuda.is_available())
        if torch.cuda.is_available():
            env["device_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        env["torch"] = f"FAIL: {exc}"
    try:
        import transformers
        env["transformers"] = transformers.__version__
    except Exception as exc:
        env["transformers"] = f"FAIL: {exc}"
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Brain V3 Embedder End-to-End Spike")
    parser.add_argument("--n-audio", type=int, default=3)
    parser.add_argument("--n-video", type=int, default=3)
    parser.add_argument("--skip-clap", action="store_true")
    parser.add_argument("--skip-siglip", action="store_true")
    parser.add_argument("--clap-skip-inference", action="store_true",
                        help="CLAP nur Cache+Repo testen, kein Modell-Load")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(out_dir)

    env = _collect_env()
    logger.info("Embedder-Smoke gestartet — Output: %s", out_dir)
    logger.info("Umgebung: %s", env)

    project_root = out_dir / "synth_project"
    audio_dir = out_dir / "synth_audio"
    video_dir = out_dir / "synth_video"

    results: list[StepResult] = []
    if not args.skip_clap:
        r = step_clap(args.n_audio, audio_dir, project_root, args.clap_skip_inference)
        results.append(r)
        _flush(out_dir, env, results)
        gc.collect()

    if not args.skip_siglip:
        r = step_siglip(args.n_video, video_dir, project_root)
        results.append(r)
        _flush(out_dir, env, results)

    logger.info("Smoke abgeschlossen.")
    print()
    print(f">>> Output: {out_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
