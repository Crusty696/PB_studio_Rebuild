"""SigLIP-only GPU test — isolates SigLIP from RAFT (no preceding VRAM pressure).

Phase 4.4 of REAL_DATA_TESTBERICHT_2026-04-13.md follow-up.

Pipeline under test:
    detect_scenes -> extract_keyframes -> generate_embeddings (GPU)

No RAFT beforehand, so the original "SigLIP OOM after RAFT" scenario is avoided.
This proves SigLIP on GTX 1060 works when it gets a clean VRAM slate.
"""

import os
import sys
import time
import tempfile
import shutil
import traceback
from pathlib import Path

# Bootstrap
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["PATH"] = str(PROJECT_ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")

# Optional video file override
VIDEO_FILE = os.environ.get(
    "PB_TEST_VIDEO",
    r"C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur\20250612_2128_Neon_Jungle_Dreamscape_v1.mp4",
)


def vram_mb():
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, total = torch.cuda.mem_get_info(0)
        return {
            "free_mb": round(free / 1024**2, 1),
            "total_mb": round(total / 1024**2, 1),
            "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024**2, 1),
        }
    except Exception:
        return None


def main():
    print("=" * 72)
    print("  PB STUDIO — SIGLIP-ONLY GPU TEST (Phase 4.4)")
    print(f"  Video: {VIDEO_FILE}")
    print(f"  Size:  {Path(VIDEO_FILE).stat().st_size / 1024**2:.1f} MB")
    print("=" * 72)

    # ── Pre-flight ──────────────────────────────────────────────────
    try:
        import torch
    except Exception as e:
        print(f"FAIL torch import: {e}")
        return

    if not torch.cuda.is_available():
        print("FAIL — CUDA not available; test requires GPU")
        return

    print(f"GPU:    {torch.cuda.get_device_name(0)}")
    print(f"Torch:  {torch.__version__}")
    print(f"CUDA:   {torch.version.cuda}")
    print(f"VRAM:   {vram_mb()}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="pb_siglip_test_"))
    keyframe_dir = tmp_dir / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    t_total = time.perf_counter()

    try:
        from services.video_analysis_service import (
            detect_scenes,
            extract_keyframes,
            generate_embeddings,
        )

        # ── Step 1: detect_scenes ───────────────────────────────────
        print("\n>>> Step 1: detect_scenes()")
        t0 = time.perf_counter()
        scenes = detect_scenes(VIDEO_FILE)
        dt = time.perf_counter() - t0
        print(f"    scenes={len(scenes)} in {dt:.1f}s")
        results["detect_scenes"] = {"status": "PASS", "elapsed": round(dt, 2), "count": len(scenes)}

        if not scenes:
            print("    No scenes detected — aborting")
            return

        # ── Step 2: extract_keyframes ───────────────────────────────
        print("\n>>> Step 2: extract_keyframes()")
        t0 = time.perf_counter()
        scenes = extract_keyframes(VIDEO_FILE, scenes, keyframe_dir)
        dt = time.perf_counter() - t0
        kf_count = sum(1 for s in scenes if s.keyframe_path and Path(s.keyframe_path).exists())
        print(f"    keyframes={kf_count}/{len(scenes)} in {dt:.1f}s")
        results["extract_keyframes"] = {
            "status": "PASS" if kf_count > 0 else "FAIL",
            "elapsed": round(dt, 2),
            "keyframes": kf_count,
        }

        if kf_count == 0:
            print("    No keyframes — aborting")
            return

        # ── Pre-embed VRAM ──────────────────────────────────────────
        print(f"\nVRAM before SigLIP: {vram_mb()}")

        # ── Step 3: generate_embeddings (THE test) ──────────────────
        print("\n>>> Step 3: generate_embeddings() — SigLIP GPU")
        t0 = time.perf_counter()
        try:
            scenes = generate_embeddings(scenes)
            dt = time.perf_counter() - t0
            embedded = sum(1 for s in scenes if getattr(s, "embedding", None) is not None)
            dim = None
            if embedded > 0:
                first_emb = next(s.embedding for s in scenes if getattr(s, "embedding", None) is not None)
                dim = len(first_emb) if hasattr(first_emb, "__len__") else None
            print(f"    embedded={embedded}/{len(scenes)} dim={dim} in {dt:.1f}s")
            print(f"    VRAM after:  {vram_mb()}")

            status = "PASS" if embedded > 0 else "FAIL"
            results["generate_embeddings"] = {
                "status": status,
                "elapsed": round(dt, 2),
                "embedded": embedded,
                "total": len(scenes),
                "dim": dim,
                "vram_after": vram_mb(),
            }
        except RuntimeError as e:
            dt = time.perf_counter() - t0
            err = str(e).lower()
            is_oom = "out of memory" in err or "cuda" in err
            print(f"    {'OOM' if is_oom else 'CRASH'}: {e}")
            results["generate_embeddings"] = {
                "status": "OOM" if is_oom else "CRASH",
                "elapsed": round(dt, 2),
                "error": str(e)[:500],
            }
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"    CRASH: {e}")
            traceback.print_exc()
            results["generate_embeddings"] = {
                "status": "CRASH",
                "elapsed": round(dt, 2),
                "error": str(e)[:500],
            }

    finally:
        total_elapsed = time.perf_counter() - t_total
        shutil.rmtree(tmp_dir, ignore_errors=True)

        print("\n" + "=" * 72)
        print("  SUMMARY")
        print("=" * 72)
        for name, r in results.items():
            print(f"  {name:<25} {r['status']:<6} {r['elapsed']:>6.1f}s  {r}")
        print(f"  Total: {total_elapsed:.1f}s")
        print("=" * 72)


if __name__ == "__main__":
    main()
