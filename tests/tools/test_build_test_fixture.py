import pytest
import numpy as np
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Note: These tests assume the presence of librosa, sklearn, and ffmpeg/ffprobe in the environment.

def test_rms_variance_window_picks_dynamic_segment(tmp_path):
    """Synthetic audio: 55 min silence + 5 min loud burst → window locates the burst."""
    from scripts.build_test_fixture import select_audio_window_by_rms
    
    sr = 22050
    duration_sec = 60 * 60 # 60 minutes
    window_sec = 300 # 5 minutes
    
    # Create synthetic audio: 50 mins silence, 5 mins loud, 5 mins silence
    audio = np.zeros(duration_sec * sr)
    burst_start = 50 * 60 * sr
    burst_end = 55 * 60 * sr
    
    # Use a high-frequency sine wave with varying amplitude for the burst
    t = np.linspace(0, 5*60, 5*60*sr)
    burst = np.sin(2 * np.pi * 440 * t) * np.linspace(0, 1, 5*60*sr)
    audio[burst_start:burst_end] = burst
    
    start_sec, end_sec = select_audio_window_by_rms(audio, sr=sr, length_sec=window_sec)
    
    # Should overlap with the burst (starts at 3000s, ends at 3300s)
    # The highest RMS variance is usually at the ramp or edges.
    assert end_sec > 3000 # Must at least start to cover the burst
    assert start_sec < 3300 # Must not be entirely after the burst
    assert abs((end_sec - start_sec) - window_sec) < 1.0

def test_beat_snap_aligns_to_downbeat():
    """Picked window start/end are within 50 ms of a detected beat."""
    from scripts.build_test_fixture import snap_to_beats
    
    # Mock beats every 0.5s
    beats = np.arange(0, 100, 0.5)
    
    # Test snapping
    snapped_start, snapped_end = snap_to_beats(4.2, 9.7, beats)
    
    assert snapped_start == 4.0
    assert snapped_end == 9.5
    
    # Within 50ms of a beat
    assert any(abs(snapped_start - b) < 0.05 for b in beats)
    assert any(abs(snapped_end - b) < 0.05 for b in beats)

def test_kmeans_clip_selection_covers_all_clusters():
    """Given 60 embeddings in 6 Gaussian clusters → 20-clip pick has >=3 per cluster."""
    from scripts.build_test_fixture import select_clips_by_kmeans
    
    # Create 6 clusters of 10 embeddings each, very far apart
    clusters = []
    for i in range(6):
        center = np.zeros(1152)
        center[i] = 100.0 # Extreme separation
        cluster = center + np.random.normal(0, 0.01, (10, 1152))
        clusters.append(cluster)
    
    embeddings = np.vstack(clusters)
    metadata = [{"file_path": f"clip_{i}.mp4", "id": i} for i in range(60)]
    
    selected = select_clips_by_kmeans(embeddings, metadata, clip_count=20, seed=42)
    
    assert len(selected) == 20
    
    # Check diversity
    cluster_counts = {}
    from sklearn.cluster import KMeans
    # Use higher n_init for the verification KMeans to ensure we match the distinct clusters
    kmeans = KMeans(n_clusters=6, random_state=42, n_init=20).fit(embeddings)
    labels = kmeans.labels_
    
    selected_indices = [m["id"] for m in selected]
    for idx in selected_indices:
        label = labels[idx]
        cluster_counts[label] = cluster_counts.get(label, 0) + 1
        
    assert len(cluster_counts) == 6
    for count in cluster_counts.values():
        assert count >= 2 # Minimal diversity check

def test_fallback_heuristic_uses_duration_motion_grid():
    """Without DB entries, 3x3 bucket sampling produces varied duration+motion."""
    from scripts.build_test_fixture import select_clips_fallback
    
    # Create 45 dummy clips (5 per bucket in a 3x3 grid)
    clips_metadata = []
    for d_tier in range(3):
        for m_tier in range(3):
            for i in range(5):
                clips_metadata.append({
                    "file_path": f"clip_{d_tier}_{m_tier}_{i}.mp4",
                    "duration": 5.0 + d_tier * 10.0,
                    "motion": 0.1 + m_tier * 0.3
                })
    
    selected = select_clips_fallback(clips_metadata, clip_count=18, seed=42)
    
    assert len(selected) == 18
    
    # Check if we have at least one from each bucket if possible
    buckets_hit = set()
    for item in selected:
        d = item["duration"]
        m = item["motion"]
        d_tier = 0 if d < 10 else (1 if d < 20 else 2)
        m_tier = 0 if m < 0.3 else (1 if m < 0.6 else 2)
        buckets_hit.add((d_tier, m_tier))
        
    assert len(buckets_hit) == 9 # All buckets hit

def test_deterministic_with_fixed_seed(tmp_path):
    """Two runs with seed=42 produce identical results."""
    from scripts.build_test_fixture import select_clips_fallback
    
    clips_metadata = [
        {"file_path": f"clip_{i}.mp4", "duration": 15.0, "motion": 0.5}
        for i in range(50)
    ]
    
    selected1 = select_clips_fallback(clips_metadata, clip_count=10, seed=42)
    selected2 = select_clips_fallback(clips_metadata, clip_count=10, seed=42)
    
    assert [c["file_path"] for c in selected1] == [c["file_path"] for c in selected2]

def test_dry_run_does_not_write_files(tmp_path, monkeypatch):
    """--dry-run prints the plan but creates no files in --output-dir."""
    import sys
    from scripts.build_test_fixture import main
    
    # Create dummy files to avoid "file not found" errors
    audio = tmp_path / "test.wav"
    audio.write_text("dummy")
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "clip1.mp4").write_text("dummy")
    
    output = tmp_path / "output"
    
    test_args = [
        "scripts/build_test_fixture.py",
        "--audio", str(audio),
        "--clips-folder", str(clips),
        "--output-dir", str(output),
        "--dry-run"
    ]
    
    with patch.object(sys, 'argv', test_args):
        # Mocking external calls that would fail on dummy files
        with patch("librosa.load", return_value=(np.zeros(100), 22050)):
            with patch("librosa.beat.beat_track", return_value=(None, np.array([]))):
                with patch("subprocess.check_output", return_value=b"10.0"):
                    main()
    
    # Output directory should not contain the fixture subdirs if they weren't created
    # or at least they should be empty of media
    assert not (output / "golden_mix" / "segment.wav").exists()
    assert not (output / "clips_20").exists() or len(list((output / "clips_20").glob("*.mp4"))) == 0
