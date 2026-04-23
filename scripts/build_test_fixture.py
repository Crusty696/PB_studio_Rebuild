#!/usr/bin/env python3
"""
scripts/build_test_fixture.py

Reproducible test fixture builder that selects a 5-minute audio segment 
and 20 diverse video clips from a user's library.
"""

import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

import numpy as np
import librosa
from sklearn.cluster import KMeans
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from database.models import AudioTrack, VideoClip, StructureSegment, Beatgrid, Scene
from database.session import nullpool_session
from services.vector_db_service import VectorDBService

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Audio Selection Helpers ---

def select_audio_window_by_rms(audio: np.ndarray, sr: int, length_sec: int) -> Tuple[float, float]:
    """Path B: Pick window with maximum RMS variance."""
    hop_length = sr # 1 second hops
    rms = librosa.feature.rms(y=audio, frame_length=sr, hop_length=hop_length)[0]
    
    window_frames = length_sec
    if len(rms) <= window_frames:
        return 0.0, float(len(audio)) / sr
    
    max_var = -1.0
    best_start_frame = 0
    
    for i in range(len(rms) - window_frames + 1):
        window = rms[i:i+window_frames]
        variance = np.var(window)
        if variance > max_var:
            max_var = variance
            best_start_frame = i
            
    start_sec = float(best_start_frame)
    end_sec = start_sec + length_sec
    return start_sec, end_sec

def snap_to_beats(start_sec: float, end_sec: float, beats: np.ndarray) -> Tuple[float, float]:
    """Snap start/end times to nearest beats."""
    if len(beats) == 0:
        return start_sec, end_sec
        
    snapped_start = beats[np.argmin(np.abs(beats - start_sec))]
    snapped_end = beats[np.argmin(np.abs(beats - end_sec))]
    return float(snapped_start), float(snapped_end)

def select_audio_segment_db(audio_path: str, length_sec: int, session: Session) -> Optional[Tuple[float, float, str]]:
    """Path A: Use DB structure segments."""
    track = session.query(AudioTrack).filter(AudioTrack.file_path == audio_path).first()
    if not track or not track.structure_segments:
        return None
        
    segments = sorted(track.structure_segments, key=lambda x: x.start_time)
    
    best_drop = None
    for seg in segments:
        if seg.label.upper() == 'DROP':
            if not best_drop or (seg.end_time - seg.start_time) > (best_drop.end_time - best_drop.start_time):
                best_drop = seg
    
    if not best_drop:
        mid = track.duration / 2
        start = max(0, mid - length_sec / 2)
        end = min(track.duration, start + length_sec)
    else:
        drop_mid = (best_drop.start_time + best_drop.end_time) / 2
        start = max(0, drop_mid - length_sec / 2)
        end = min(track.duration, start + length_sec)
        
    if track.beatgrid and track.beatgrid.downbeat_positions:
        downbeats = np.array(track.beatgrid.downbeat_positions)
        start, end = snap_to_beats(start, end, downbeats)
    elif track.beatgrid and track.beatgrid.beat_positions:
        beats = np.array(track.beatgrid.beat_positions)
        start, end = snap_to_beats(start, end, beats)
        
    return start, end, "db_structure_arc"

# --- Clip Selection Helpers ---

def select_clips_by_kmeans(embeddings: np.ndarray, metadata: List[Dict], clip_count: int, seed: int) -> List[Dict]:
    """Path A: Select diverse clips using K-Means clustering on SigLIP embeddings."""
    k = min(6, len(metadata))
    kmeans = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(embeddings)
    labels = kmeans.labels_
    centroids = kmeans.cluster_centers_
    
    cluster_map: Dict[int, List[int]] = {}
    for i in range(k):
        cluster_indices = np.where(labels == i)[0]
        if len(cluster_indices) > 0:
            cluster_embs = embeddings[cluster_indices]
            distances = np.linalg.norm(cluster_embs - centroids[i], axis=1)
            sorted_indices = cluster_indices[np.argsort(distances)]
            cluster_map[i] = sorted_indices.tolist()
    
    selected_clips: List[Dict] = []
    active_clusters = sorted(cluster_map.keys())
    
    while len(selected_clips) < clip_count and active_clusters:
        for i in list(active_clusters):
            if cluster_map[i]:
                idx = cluster_map[i].pop(0)
                selected_clips.append(metadata[idx])
                if len(selected_clips) == clip_count:
                    break
            else:
                active_clusters.remove(i)
                
    if len(selected_clips) < clip_count:
        already_selected_paths = {c.get("file_path") or c.get("video_path") for c in selected_clips}
        remaining_indices = [i for i, m in enumerate(metadata) if (m.get("file_path") or m.get("video_path")) not in already_selected_paths]
        
        while len(selected_clips) < clip_count and remaining_indices:
            random.seed(seed + len(selected_clips))
            idx = random.choice(remaining_indices)
            selected_clips.append(metadata[idx])
            remaining_indices.remove(idx)
            
    return selected_clips

def select_clips_fallback(clips_metadata: List[Dict], clip_count: int, seed: int) -> List[Dict]:
    """Path B: 3x3 Grid (duration x motion) sampling."""
    buckets: Dict[Tuple[int, int], List[Dict]] = {}
    for clip in clips_metadata:
        d = clip["duration"]
        m = clip["motion"]
        d_tier = 0 if d < 10 else (1 if d < 20 else 2)
        m_tier = 0 if m < 0.3 else (1 if m < 0.6 else 2)
        key = (d_tier, m_tier)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(clip)
        
    active_buckets = list(buckets.keys())
    if not active_buckets:
        return []
        
    random.seed(seed)
    selected_clips: List[Dict] = []
    
    while len(selected_clips) < clip_count and active_buckets:
        for key in list(active_buckets):
            if buckets[key]:
                idx = random.randint(0, len(buckets[key]) - 1)
                selected_clips.append(buckets[key].pop(idx))
                if len(selected_clips) == clip_count:
                    break
            else:
                active_buckets.remove(key)
                
    return selected_clips

# --- Core Logic ---

def main():
    parser = argparse.ArgumentParser(description="Build reproducible test fixtures.")
    parser.add_argument("--audio", required=True, help="Path to source 1h-mix WAV")
    parser.add_argument("--clips-folder", required=True, help="Path to source clips directory")
    parser.add_argument("--audio-length", type=int, default=300, help="Target segment length in seconds")
    parser.add_argument("--clip-count", type=int, default=20, help="Number of clips to select")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for determinism")
    parser.add_argument("--output-dir", required=True, help="Directory to write fixtures")
    parser.add_argument("--dry-run", action="store_true", help="Print plan but do not copy files")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    audio_src = Path(args.audio)
    clips_src = Path(args.clips_folder)
    
    if not audio_src.exists():
        logger.error(f"Audio file not found: {audio_src}")
        sys.exit(1)
    if not clips_src.is_dir():
        logger.error(f"Clips folder not found: {clips_src}")
        sys.exit(1)
        
    # 1. Audio Selection
    logger.info("Selecting audio segment...")
    audio_start = 0.0
    audio_end = float(args.audio_length)
    audio_criterion = "fallback_rms"
    
    with nullpool_session() as session:
        db_res = select_audio_segment_db(str(audio_src), args.audio_length, session)
        if db_res:
            audio_start, audio_end, audio_criterion = db_res
            logger.info(f"Using DB structure for audio selection: {audio_start:.2f} to {audio_end:.2f}")
        else:
            logger.info("No DB info found for audio, using RMS fallback...")
            y, sr = librosa.load(str(audio_src), sr=22050, mono=True)
            audio_start, audio_end = select_audio_window_by_rms(y, sr, args.audio_length)
            beats = librosa.beat.beat_track(y=y, sr=sr)[1]
            beat_times = librosa.frames_to_time(beats, sr=sr)
            audio_start, audio_end = snap_to_beats(audio_start, audio_end, beat_times)
            logger.info(f"RMS selected window: {audio_start:.2f} to {audio_end:.2f}")

    # 2. Clip Selection
    logger.info("Selecting diverse clips...")
    selected_clips: List[Dict] = []
    clip_selection_method = "fallback_grid"
    
    vdb = VectorDBService()
    all_embs, all_meta = vdb.get_all_embeddings()
    
    src_folder_abs = clips_src.resolve()
    filtered_indices = []
    for i, meta in enumerate(all_meta):
        meta_path = Path(meta["video_path"]).resolve()
        try:
            if meta_path.is_relative_to(src_folder_abs):
                filtered_indices.append(i)
        except ValueError:
            continue
            
    if len(filtered_indices) >= args.clip_count:
        f_embs = all_embs[filtered_indices]
        f_meta = [all_meta[i] for i in filtered_indices]
        selected_clips = select_clips_by_kmeans(f_embs, f_meta, args.clip_count, args.seed)
        clip_selection_method = "kmeans_siglip"
        logger.info(f"Selected {len(selected_clips)} clips using K-Means clustering.")
    else:
        logger.info("Insufficient DB data for K-Means, using fallback grid...")
        fallback_meta = []
        for f in clips_src.glob("*.mp4"):
            try:
                dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(f)]
                duration = float(subprocess.check_output(dur_cmd).decode().strip())
                motion = 0.5 
                fallback_meta.append({
                    "file_path": str(f),
                    "duration": duration,
                    "motion": motion
                })
            except Exception as e:
                logger.warning(f"Failed to probe {f}: {e}")
                
        selected_clips = select_clips_fallback(fallback_meta, args.clip_count, args.seed)
        clip_selection_method = "fallback_3x3_grid"

    # 3. Output Generation
    if args.dry_run:
        logger.info("DRY RUN: No files will be written.")
        logger.info(f"Plan: Audio {audio_start:.2f}-{audio_end:.2f} ({audio_criterion})")
        logger.info(f"Plan: {len(selected_clips)} clips selected via {clip_selection_method}")
        for c in selected_clips:
            path = c.get('file_path') or c.get('video_path')
            logger.info(f"  - {path}")
        return

    golden_dir = output_dir / "golden_mix"
    clips_dir = output_dir / "clips_20"
    golden_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Cutting audio segment...")
    seg_path = golden_dir / "segment.wav"
    duration = audio_end - audio_start
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(audio_start), "-t", str(duration),
        "-i", str(audio_src), str(seg_path)
    ], check=True, capture_output=True)
    
    with open(golden_dir / "selection_report.md", "w") as f:
        f.write(f"# Audio Selection Report\n\n")
        f.write(f"- **Start:** {audio_start:.3f} s\n")
        f.write(f"- **End:** {audio_end:.3f} s\n")
        f.write(f"- **Duration:** {duration:.3f} s\n")
        f.write(f"- **Criterion:** {audio_criterion}\n")
        
    with open(golden_dir / "source_provenance.json", "w") as f:
        json.dump({
            "source_audio_path": str(audio_src.resolve()),
            "chosen_window": [audio_start, audio_end],
            "seed": args.seed
        }, f, indent=2)
        
    logger.info("Copying clips...")
    clip_details = []
    for i, clip in enumerate(selected_clips):
        path_val = clip.get("file_path") or clip.get("video_path")
        src_path = Path(path_val)
        dest_name = f"clip_{i+1:02d}_{src_path.name}"
        dest_path = clips_dir / dest_name
        shutil.copy2(src_path, dest_path)
        
        clip_details.append({
            "original": str(src_path),
            "chosen": dest_name,
            "metadata": clip
        })
        
    with open(clips_dir / "selection_report.md", "w") as f:
        f.write(f"# Clip Selection Report\n\n")
        f.write(f"Method: {clip_selection_method}\n\n")
        f.write("| Index | Name | Original Path | Info |\n")
        f.write("|-------|------|---------------|------|\n")
        for i, detail in enumerate(clip_details):
            f.write(f"| {i+1} | {detail['chosen']} | {detail['original']} | {detail['metadata']} |\n")
            
    with open(clips_dir / "source_provenance.json", "w") as f:
        json.dump({
            "source_folder": str(clips_src.resolve()),
            "files_chosen": [d["original"] for d in clip_details],
            "seed": args.seed
        }, f, indent=2)
        
    logger.info(f"Done! Fixtures written to {output_dir}")

if __name__ == "__main__":
    main()
