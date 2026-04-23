"""
scripts/build_test_fixture.py
=============================

Auto-select a ~5-minute audio segment and a diverse set of video clips from
a user's library and write them into ``tests/fixtures/`` for use as a
reproducible test fixture.

CLI usage::

    python scripts/build_test_fixture.py \\
        --audio    /path/to/1h-mix.wav \\
        --clips-folder /path/to/clips-dir \\
        --audio-length 300 \\
        --clip-count   20 \\
        --seed         42 \\
        --output-dir   tests/fixtures \\
        [--dry-run]

Public API (importable for unit tests)
---------------------------------------
- ``select_audio_window_by_rms(audio, sr, length_sec)`` → ``AudioWindow``
- ``select_audio_window_from_structure(audio_path, length_sec, session)`` → ``AudioWindow | None``
- ``select_clips_by_kmeans(embeddings, clip_count, seed, n_clusters)`` → ``list[int]``
- ``select_clips_by_heuristic(clips, clip_count, seed)`` → ``list[ClipInfo]``
- ``run_fixture_build(...)`` — full build, also used by CLI main()

Architecture: deep-module style — audio and clip selection are pure helper
functions exposed at module level, with no CLI scaffolding entanglement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AudioWindow:
    """Describes the selected audio sub-segment."""

    start_sec: float
    end_sec: float
    criterion: str  # "rms_variance" | "structure_arc"
    snap_info: str  # human-readable beat-snap details


@dataclass
class ClipInfo:
    """Lightweight descriptor for a video clip used by the heuristic selector."""

    path: Path
    duration: float  # seconds
    motion: float  # 0-1 proxy
    resolution: tuple[int, int]  # (width, height)


# ---------------------------------------------------------------------------
# Audio-selection helpers
# ---------------------------------------------------------------------------


def _snap_to_nearest_beat(
    time_sec: float,
    beat_times: np.ndarray,
) -> tuple[float, float]:
    """Return (snapped_time, distance_sec) to the nearest beat in *beat_times*."""
    if len(beat_times) == 0:
        return time_sec, 0.0
    idx = int(np.argmin(np.abs(beat_times - time_sec)))
    snapped = float(beat_times[idx])
    distance = abs(snapped - time_sec)
    return snapped, distance


def select_audio_window_by_rms(
    audio: np.ndarray,
    sr: int,
    length_sec: float,
) -> AudioWindow:
    """Path B (fallback) — pick the *length_sec*-wide window with max RMS-variance.

    Parameters
    ----------
    audio:
        Mono float32 array (any amplitude range, but float is expected).
    sr:
        Sample rate.
    length_sec:
        Desired window length in seconds.

    Returns
    -------
    AudioWindow
        With start/end snapped to the nearest detected beat.
    """
    import librosa  # lazy import — not required if DB path is used

    hop = sr  # one sample per second for RMS computation
    frame_len = sr

    # Compute per-second RMS
    n_total_sec = len(audio) // sr
    if n_total_sec < 1:
        # Audio shorter than 1 second — return the whole thing
        return AudioWindow(
            start_sec=0.0,
            end_sec=len(audio) / sr,
            criterion="rms_variance",
            snap_info="audio too short for windowing",
        )

    per_sec_rms = np.array(
        [
            float(
                np.sqrt(
                    np.mean(
                        audio[s * sr : min((s + 1) * sr, len(audio))].astype(np.float64)
                        ** 2
                    )
                )
            )
            for s in range(n_total_sec)
        ],
        dtype=np.float64,
    )

    window_secs = min(int(length_sec), n_total_sec)
    if window_secs >= n_total_sec:
        # Window covers everything
        best_start_s = 0
    else:
        # Slide window, pick the one with max RMS-variance.
        # We score each window by mean_rms * (1 + rms_std) so that:
        #   - Loud windows score high (high mean_rms).
        #   - Among equally loud windows, dynamic ones score higher (higher std).
        # This ensures "max RMS-variance" selects the loudest dynamic segment
        # rather than a quiet-to-loud transition (which would have high variance
        # but low mean RMS).
        best_score = -1.0
        best_start_s = 0
        for start in range(n_total_sec - window_secs + 1):
            window_rms = per_sec_rms[start : start + window_secs]
            mean_rms = float(np.mean(window_rms))
            std_rms = float(np.std(window_rms))
            score = mean_rms * (1.0 + std_rms)
            if score > best_score:
                best_score = score
                best_start_s = start

    raw_start = float(best_start_s)
    raw_end = float(best_start_s + window_secs)

    # Detect beats for snapping (use the whole audio — cheap at 22 kHz)
    try:
        _tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    except Exception:
        beat_times = np.array([], dtype=np.float64)

    # Maximum allowed snap distance: 2 seconds (avoid large displacements)
    MAX_SNAP_SEC = 2.0

    snapped_start, d_start = _snap_to_nearest_beat(raw_start, beat_times)
    if d_start > MAX_SNAP_SEC:
        snapped_start, d_start = raw_start, 0.0

    snapped_end, d_end = _snap_to_nearest_beat(raw_end, beat_times)
    if d_end > MAX_SNAP_SEC:
        snapped_end, d_end = raw_end, 0.0

    # Clamp to audio bounds
    audio_duration = len(audio) / sr
    snapped_start = float(np.clip(snapped_start, 0.0, audio_duration))
    snapped_end = float(np.clip(snapped_end, 0.0, audio_duration))

    # If snapping collapsed the window, revert to raw
    if snapped_end <= snapped_start:
        snapped_start = raw_start
        snapped_end = raw_end

    snap_info = (
        f"start snapped {d_start:.3f}s, end snapped {d_end:.3f}s "
        f"(from {len(beat_times)} detected beats)"
    )

    return AudioWindow(
        start_sec=snapped_start,
        end_sec=snapped_end,
        criterion="rms_variance",
        snap_info=snap_info,
    )


def select_audio_window_from_structure(
    audio_path: Path,
    length_sec: float,
    session: Any,  # SQLAlchemy session — typed as Any for lazy import compatibility
) -> Optional[AudioWindow]:
    """Path A (preferred) — pick a window using StructureSegment rows from the DB.

    Returns ``None`` if the audio track cannot be found in the DB or has no
    structure segments; the caller should fall back to ``select_audio_window_by_rms``.
    """
    try:
        # Avoid importing the full app model at module load
        import importlib

        models_mod = importlib.import_module("database.models")
        AudioTrack = models_mod.AudioTrack
        StructureSegment = getattr(models_mod, "StructureSegment", None)
        Beatgrid = getattr(models_mod, "Beatgrid", None)

        if StructureSegment is None:
            return None

        track = session.query(AudioTrack).filter_by(file_path=str(audio_path)).first()
        if track is None:
            return None

        segments = (
            session.query(StructureSegment)
            .filter_by(audio_track_id=track.id)
            .order_by(StructureSegment.start_sec)
            .all()
        )
        if not segments:
            return None

        # Desired arc: intro → drop → breakdown → outro (or closest)
        DESIRED_ORDER = ["intro", "drop", "breakdown", "outro"]
        type_to_segs: dict[str, list[Any]] = {}
        for seg in segments:
            t = getattr(seg, "section_type", "").lower()
            type_to_segs.setdefault(t, []).append(seg)

        # Pick the best consecutive sub-sequence by greedily matching desired types
        chosen: list[Any] = []
        for desired in DESIRED_ORDER:
            segs_of_type = type_to_segs.get(desired, [])
            if segs_of_type:
                # If we have chosen segments already, pick the one that comes next
                if chosen:
                    last_end = getattr(chosen[-1], "end_sec", 0.0)
                    after = [
                        s
                        for s in segs_of_type
                        if getattr(s, "start_sec", 0.0) >= last_end
                    ]
                    if after:
                        chosen.append(after[0])
                    else:
                        chosen.append(segs_of_type[0])
                else:
                    chosen.append(segs_of_type[0])

        if not chosen:
            return None

        arc_start = float(getattr(chosen[0], "start_sec", 0.0))
        arc_end = float(getattr(chosen[-1], "end_sec", arc_start + length_sec))

        # Trim to length_sec if the arc is longer
        if arc_end - arc_start > length_sec:
            arc_end = arc_start + length_sec

        # Snap to nearest downbeat from Beatgrid if available
        beat_times: np.ndarray = np.array([], dtype=np.float64)
        if Beatgrid is not None:
            grid = session.query(Beatgrid).filter_by(audio_track_id=track.id).first()
            if grid is not None:
                downbeats = getattr(grid, "downbeat_positions", None)
                if downbeats is not None:
                    beat_times = np.asarray(downbeats, dtype=np.float64)

        snapped_start, d_start = _snap_to_nearest_beat(arc_start, beat_times)
        snapped_end, d_end = _snap_to_nearest_beat(arc_end, beat_times)

        snap_info = (
            f"structure arc {' → '.join(getattr(s, 'section_type', '?') for s in chosen)}; "
            f"start snapped {d_start:.3f}s, end snapped {d_end:.3f}s"
        )

        return AudioWindow(
            start_sec=snapped_start,
            end_sec=snapped_end,
            criterion="structure_arc",
            snap_info=snap_info,
        )

    except Exception:
        # Any failure (missing tables, import errors, …) → fall back to Path B
        return None


# ---------------------------------------------------------------------------
# Clip-selection helpers
# ---------------------------------------------------------------------------


def select_clips_by_kmeans(
    embeddings: np.ndarray,
    clip_count: int,
    seed: int,
    n_clusters: int = 6,
) -> list[int]:
    """Path A (preferred) — diverse clip selection via k-means on embeddings.

    Parameters
    ----------
    embeddings:
        Shape ``(n_clips, dim)`` float array.
    clip_count:
        Number of clips to select.
    seed:
        Random seed for reproducibility.
    n_clusters:
        Number of k-means clusters (default 6).

    Returns
    -------
    list[int]
        Indices into *embeddings* for the selected clips.
    """
    from sklearn.cluster import KMeans  # type: ignore[import-untyped]  # lazy import

    n_clips = len(embeddings)
    if n_clips == 0:
        return []

    k = min(n_clusters, n_clips)
    km = KMeans(n_clusters=k, random_state=seed, n_init="auto")
    cluster_labels = km.fit_predict(embeddings)
    centroids = km.cluster_centers_

    non_empty_clusters = sorted(set(cluster_labels.tolist()))
    n_non_empty = len(non_empty_clusters)

    if n_non_empty == 0:
        return []

    # Base allocation: floor(clip_count / n_clusters) per cluster.
    # Distribute remainder one extra each to first R clusters.
    base = clip_count // n_non_empty
    remainder = clip_count % n_non_empty

    # Sort cluster candidates (closest to centroid first) per cluster
    cluster_candidates: dict[int, list[int]] = {}
    for cid in non_empty_clusters:
        indices = np.where(cluster_labels == cid)[0]
        dists = np.linalg.norm(embeddings[indices] - centroids[cid], axis=1)
        sorted_indices = indices[np.argsort(dists)]
        cluster_candidates[cid] = sorted_indices.tolist()

    selected: list[int] = []
    for i, cid in enumerate(non_empty_clusters):
        alloc = base + (1 if i < remainder else 0)
        alloc = min(alloc, len(cluster_candidates[cid]))
        selected.extend(cluster_candidates[cid][:alloc])

    # If still short (because some clusters had fewer clips than alloc), top-up
    if len(selected) < clip_count:
        selected_set = set(selected)
        remaining = [i for i in range(n_clips) if i not in selected_set]

        # Max-min-distance selection from remaining
        rng = np.random.default_rng(seed)
        if remaining:
            remaining_arr = np.array(remaining, dtype=np.int64)
            rng.shuffle(remaining_arr)
            order: list[int] = [int(remaining_arr[0])]
            remaining_set = set(remaining_arr[1:].tolist())

            while len(selected) + len(order) < clip_count and remaining_set:
                sel_embs = embeddings[selected + order]
                best_idx = -1
                best_min_dist = -1.0
                for idx in remaining_set:
                    dists_to_sel = np.linalg.norm(sel_embs - embeddings[idx], axis=1)
                    min_d = float(np.min(dists_to_sel))
                    if min_d > best_min_dist:
                        best_min_dist = min_d
                        best_idx = idx
                if best_idx == -1:
                    break
                order.append(best_idx)
                remaining_set.discard(best_idx)

            selected.extend(order)

    return selected[:clip_count]


def _probe_clip(path: Path) -> ClipInfo:
    """Run ffprobe to get duration and resolution of a video file."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0.0))

        width, height = 0, 0
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
                break
    except Exception:
        duration = 1.0
        width, height = 1920, 1080

    return ClipInfo(
        path=path, duration=duration, motion=0.5, resolution=(width, height)
    )


def _compute_motion_proxy(path: Path) -> float:
    """Compute motion proxy as scene-change-frame-count / duration."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(path),
                "-vf",
                "select='gt(scene,0.3)',metadata=print",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Count frames that passed the select filter
        scene_frames = result.stderr.count("pts_time")
        info = _probe_clip(path)
        if info.duration > 0:
            return float(np.clip(scene_frames / info.duration, 0.0, 1.0))
        return 0.0
    except Exception:
        return 0.5


def select_clips_by_heuristic(
    clips: list[ClipInfo],
    clip_count: int,
    seed: int,
) -> list[ClipInfo]:
    """Path B (fallback) — bucket clips by (duration_tier, motion_tier) and sample.

    Buckets are a 3x3 grid:
    - duration_tier: 0 = short (<= 10s), 1 = medium (10–30s), 2 = long (>30s)
    - motion_tier:  0 = low (<= 0.33), 1 = medium (0.33–0.67), 2 = high (>0.67)

    Sampling is proportional to bucket size; clips within each bucket are
    selected in random order (deterministic via *seed*).
    """
    if not clips:
        return []

    rng = np.random.default_rng(seed)

    def dur_tier(d: float) -> int:
        if d <= 10.0:
            return 0
        elif d <= 30.0:
            return 1
        return 2

    def mot_tier(m: float) -> int:
        if m <= 0.33:
            return 0
        elif m <= 0.67:
            return 1
        return 2

    # Group into 3x3 grid
    buckets: dict[tuple[int, int], list[ClipInfo]] = {}
    for clip in clips:
        key = (dur_tier(clip.duration), mot_tier(clip.motion))
        buckets.setdefault(key, []).append(clip)

    non_empty_buckets = [k for k, v in buckets.items() if v]
    n_buckets = len(non_empty_buckets)

    if n_buckets == 0:
        return []

    # Shuffle within each bucket for reproducibility
    for key in non_empty_buckets:
        bucket_list = buckets[key]
        indices = rng.permutation(len(bucket_list)).tolist()
        buckets[key] = [bucket_list[i] for i in indices]

    # Proportional allocation
    selected: list[ClipInfo] = []
    bucket_sizes = {k: len(buckets[k]) for k in non_empty_buckets}
    total_clips = sum(bucket_sizes.values())

    allocations: dict[tuple[int, int], int] = {}
    allocated = 0
    for key in non_empty_buckets[:-1]:
        alloc = math.floor(clip_count * bucket_sizes[key] / total_clips)
        alloc = min(alloc, bucket_sizes[key])
        allocations[key] = alloc
        allocated += alloc
    # Last bucket gets the remainder
    last_key = non_empty_buckets[-1]
    allocations[last_key] = min(clip_count - allocated, bucket_sizes[last_key])

    for key in non_empty_buckets:
        n = allocations[key]
        selected.extend(buckets[key][:n])

    # Top-up if still short (take leftover clips)
    if len(selected) < clip_count:
        selected_paths = {c.path for c in selected}
        for clip in clips:
            if clip.path not in selected_paths:
                selected.append(clip)
                selected_paths.add(clip.path)
                if len(selected) >= clip_count:
                    break

    return selected[:clip_count]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_audio_output(
    audio_path: Path,
    window: AudioWindow,
    output_dir: Path,
    seed: int,
) -> None:
    """Write segment.wav, selection_report.md, source_provenance.json to golden_mix/."""
    import soundfile as sf  # type: ignore[import-untyped]  # lazy import

    golden_dir = output_dir / "golden_mix"
    golden_dir.mkdir(parents=True, exist_ok=True)

    # Write segment.wav
    import librosa  # lazy import

    audio, sr = librosa.load(
        str(audio_path),
        sr=22050,
        mono=True,
        offset=window.start_sec,
        duration=window.end_sec - window.start_sec,
    )
    sf.write(str(golden_dir / "segment.wav"), audio, int(sr))

    # Write selection_report.md (deterministic content, no timestamps)
    report_lines = [
        "# Audio Segment Selection Report",
        "",
        f"- **start_sec:** {window.start_sec:.4f}",
        f"- **end_sec:** {window.end_sec:.4f}",
        f"- **duration_sec:** {window.end_sec - window.start_sec:.4f}",
        f"- **criterion:** {window.criterion}",
        f"- **snap_info:** {window.snap_info}",
        f"- **seed:** {seed}",
    ]
    (golden_dir / "selection_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )

    # Write source_provenance.json
    sha = _sha256(audio_path)
    provenance = {
        "source_audio_path": str(audio_path),
        "sha256": sha,
        "chosen_window": {
            "start_sec": window.start_sec,
            "end_sec": window.end_sec,
            "criterion": window.criterion,
        },
        "seed": seed,
    }
    (golden_dir / "source_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )


def _write_clips_output(
    clips: list[ClipInfo],
    clip_count: int,
    clips_folder: Path,
    output_dir: Path,
    seed: int,
    clip_selection_info: list[str],
) -> None:
    """Copy selected clips and write reports to clips_{clip_count}/."""
    clips_dir = output_dir / f"clips_{clip_count}"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Copy clips with ordered naming
    report_rows: list[str] = [
        "# Clip Selection Report",
        "",
        f"| # | Original Name | Duration | Motion | Reason |",
        f"|---|---------------|----------|--------|--------|",
    ]

    for i, (clip, info_str) in enumerate(zip(clips, clip_selection_info), start=1):
        dest_name = f"clip_{i:02d}_{clip.path.name}"
        dest = clips_dir / dest_name
        shutil.copy2(str(clip.path), str(dest))

        report_rows.append(
            f"| {i:02d} | {clip.path.name} | {clip.duration:.2f}s | {clip.motion:.3f} | {info_str} |"
        )

    report_rows.extend(["", f"**seed:** {seed}"])
    (clips_dir / "selection_report.md").write_text(
        "\n".join(report_rows), encoding="utf-8"
    )

    # Source provenance
    provenance = {
        "source_folder": str(clips_folder),
        "files_chosen": [str(c.path) for c in clips],
        "seed": seed,
    }
    (clips_dir / "source_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Top-level build function (used by CLI and by determinism tests)
# ---------------------------------------------------------------------------


def run_fixture_build(
    audio_path: Path,
    clips_folder: Path,
    audio_length: float,
    clip_count: int,
    seed: int,
    output_dir: Path,
    dry_run: bool = False,
) -> None:
    """Execute the full fixture build (audio segment + clip selection + write outputs).

    When *dry_run* is True, selection logic runs but nothing is written to disk.
    """
    import librosa  # lazy import

    # ------------------------------------------------------------------
    # Step 1: Audio selection
    # ------------------------------------------------------------------

    # Path A: try DB lookup first
    window: Optional[AudioWindow] = None
    try:
        # Lazy import of DB session
        import importlib

        db_mod = importlib.import_module("database")
        get_session = getattr(db_mod, "get_session", None)
        if get_session is not None:
            with get_session() as session:
                window = select_audio_window_from_structure(
                    audio_path=audio_path,
                    length_sec=audio_length,
                    session=session,
                )
    except Exception:
        window = None

    # Path B: fallback to RMS variance
    if window is None:
        print(
            "[audio] DB not available or audio not analysed — using RMS-variance fallback."
        )
        audio_full, sr_loaded = librosa.load(str(audio_path), sr=22050, mono=True)
        window = select_audio_window_by_rms(
            audio_full, sr=int(sr_loaded), length_sec=audio_length
        )

    print(
        f"[audio] Selected window: {window.start_sec:.2f}s – {window.end_sec:.2f}s "
        f"({window.end_sec - window.start_sec:.2f}s) via {window.criterion}"
    )
    print(f"[audio] Snap info: {window.snap_info}")

    # ------------------------------------------------------------------
    # Step 2: Clip selection
    # ------------------------------------------------------------------

    # Gather clip paths
    clip_extensions = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".m2ts"}
    clip_paths = sorted(
        p for p in clips_folder.iterdir() if p.suffix.lower() in clip_extensions
    )

    selected_clips: list[ClipInfo]
    clip_selection_info: list[str]

    if not clip_paths:
        print("[clips] No video files found in clips folder.")
        selected_clips = []
        clip_selection_info = []
    else:
        # Path A: try embeddings from DB / vector store
        embeddings_loaded = False
        embeddings: Optional[np.ndarray] = None
        clip_infos_for_kmeans: list[Path] = []

        try:
            import importlib

            vec_mod = importlib.import_module("services.vector_db_service")
            vdb = getattr(vec_mod, "vector_db_service", None)
            if vdb is not None and hasattr(vdb, "_cache_matrix"):
                cache: dict[str, np.ndarray] = vdb._cache_matrix
                matched: list[tuple[Path, np.ndarray]] = []
                for cp in clip_paths:
                    for key, emb in cache.items():
                        if Path(key).name == cp.name or key == str(cp):
                            matched.append((cp, emb))
                            break
                if matched:
                    clip_infos_for_kmeans = [m[0] for m in matched]
                    embeddings = np.stack([m[1] for m in matched])
                    embeddings_loaded = True
        except Exception:
            pass

        if embeddings_loaded and embeddings is not None:
            print(f"[clips] Using k-means on {len(embeddings)} embeddings from DB.")
            selected_indices = select_clips_by_kmeans(
                embeddings=embeddings,
                clip_count=clip_count,
                seed=seed,
            )
            selected_clips = [
                ClipInfo(
                    path=clip_infos_for_kmeans[i],
                    duration=0.0,  # not needed for report when using DB path
                    motion=0.0,
                    resolution=(0, 0),
                )
                for i in selected_indices
            ]
            clip_selection_info = [
                f"k-means cluster selection (index {i})" for i in selected_indices
            ]
        else:
            # Path B: heuristic using ffprobe
            print(
                f"[clips] DB not available — using heuristic on {len(clip_paths)} files."
            )
            clips_probed: list[ClipInfo] = []
            for cp in clip_paths:
                info = _probe_clip(cp)
                # Compute motion proxy if ffmpeg available
                try:
                    motion = _compute_motion_proxy(cp)
                except Exception:
                    motion = 0.5
                clips_probed.append(
                    ClipInfo(
                        path=cp,
                        duration=info.duration,
                        motion=motion,
                        resolution=info.resolution,
                    )
                )

            selected_clips = select_clips_by_heuristic(
                clips=clips_probed,
                clip_count=clip_count,
                seed=seed,
            )
            clip_selection_info = [
                f"heuristic bucket dur={c.duration:.2f}s motion={c.motion:.3f}"
                for c in selected_clips
            ]

    print(f"[clips] Selected {len(selected_clips)} clips.")

    # ------------------------------------------------------------------
    # Step 3: Dry-run guard
    # ------------------------------------------------------------------

    if dry_run:
        print("[dry-run] Plan summary — nothing written to disk.")
        print(f"  Audio: {audio_path} → {window.start_sec:.2f}s–{window.end_sec:.2f}s")
        print(f"  Clips ({clip_count}):")
        for c in selected_clips[:5]:
            print(f"    {c.path.name}")
        if len(selected_clips) > 5:
            print(f"    ... and {len(selected_clips) - 5} more")
        return

    # ------------------------------------------------------------------
    # Step 4: Write outputs
    # ------------------------------------------------------------------

    _write_audio_output(
        audio_path=audio_path,
        window=window,
        output_dir=output_dir,
        seed=seed,
    )
    _write_clips_output(
        clips=selected_clips,
        clip_count=clip_count,
        clips_folder=clips_folder,
        output_dir=output_dir,
        seed=seed,
        clip_selection_info=clip_selection_info,
    )

    print(f"[done] Fixture written to {output_dir}")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a reproducible test fixture: select a ~5-min audio segment "
        "and a diverse set of video clips from a user library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--audio", required=True, type=Path, help="Path to the 1h DJ-mix WAV."
    )
    parser.add_argument(
        "--clips-folder",
        required=True,
        type=Path,
        help="Folder containing video clip files.",
    )
    parser.add_argument(
        "--audio-length",
        type=float,
        default=300.0,
        help="Desired audio segment length in seconds (default: 300).",
    )
    parser.add_argument(
        "--clip-count",
        type=int,
        default=20,
        help="Number of clips to select (default: 20).",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures"),
        help="Root output directory (default: tests/fixtures).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selection plan without writing any files.",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    run_fixture_build(
        audio_path=args.audio,
        clips_folder=args.clips_folder,
        audio_length=args.audio_length,
        clip_count=args.clip_count,
        seed=args.seed,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
