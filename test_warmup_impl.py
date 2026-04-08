"""Quick verification script for WARMUP section detection (F-005)."""

import sys
import numpy as np
from services.structure_detection_service import StructureDetectionService, SEGMENT_LABELS
from services.audio_constants import (
    WARMUP_ENERGY_MIN, WARMUP_ENERGY_MAX, WARMUP_MIN_BEATS,
    WARMUP_MAX_POSITION, WARMUP_GRADIENT_MIN, WARMUP_CENTROID_RISING,
)

def test_constants():
    """Verify WARMUP constants are defined."""
    print("✓ Testing WARMUP constants...")
    assert WARMUP_ENERGY_MIN == 0.3, f"Expected 0.3, got {WARMUP_ENERGY_MIN}"
    assert WARMUP_ENERGY_MAX == 0.55, f"Expected 0.55, got {WARMUP_ENERGY_MAX}"
    assert WARMUP_MIN_BEATS == 8, f"Expected 8, got {WARMUP_MIN_BEATS}"
    assert WARMUP_MAX_POSITION == 0.4, f"Expected 0.4, got {WARMUP_MAX_POSITION}"
    assert WARMUP_GRADIENT_MIN == 0.005, f"Expected 0.005, got {WARMUP_GRADIENT_MIN}"
    assert WARMUP_CENTROID_RISING == 0.4, f"Expected 0.4, got {WARMUP_CENTROID_RISING}"
    print("  All constants OK!")

def test_segment_labels():
    """Verify WARMUP is in SEGMENT_LABELS."""
    print("\n✓ Testing SEGMENT_LABELS...")
    assert "WARMUP" in SEGMENT_LABELS, f"WARMUP not in {SEGMENT_LABELS}"
    required = ["INTRO", "WARMUP", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO"]
    for label in required:
        assert label in SEGMENT_LABELS, f"{label} missing from SEGMENT_LABELS"
    print(f"  SEGMENT_LABELS: {SEGMENT_LABELS}")
    print("  All required labels present!")

def test_warmup_detection():
    """Test WARMUP detection with synthetic energy curve."""
    print("\n✓ Testing WARMUP detection logic...")

    svc = StructureDetectionService()
    n_beats = 200
    energy = []

    # INTRO: Beats 0-15 (low energy)
    energy.extend([0.15] * 15)

    # WARMUP: Beats 15-45 (moderate energy, gentle rise 0.3→0.5)
    for i in range(30):
        energy.append(0.3 + (i / 30) * 0.2)

    # BUILDUP: Beats 45-70 (steeper rise 0.5→0.85)
    for i in range(25):
        energy.append(0.5 + (i / 25) * 0.35)

    # DROP: Beats 70-120 (high)
    energy.extend([0.88] * 50)

    # BREAKDOWN: Beats 120-160 (low)
    energy.extend([0.28] * 40)

    # VERSE/CHORUS: Beats 160-180 (medium)
    energy.extend([0.45] * 20)

    # OUTRO: Beats 180-200 (low)
    energy.extend([0.12] * 20)

    beats = [i * 0.5 for i in range(n_beats)]  # 120 BPM

    print(f"  Testing with {n_beats} beats, {len(energy)} energy values...")
    result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)

    print(f"  Detected {len(result.segments)} segments:")
    for seg in result.segments:
        print(f"    {seg.label:12s} {seg.start_time:6.1f}s - {seg.end_time:6.1f}s "
              f"(energy={seg.energy:.2f}, conf={seg.confidence:.2f})")

    # Check WARMUP was detected
    labels = [s.label for s in result.segments]
    assert "WARMUP" in labels, f"WARMUP not detected! Labels: {labels}"

    # Check WARMUP is early in track
    warmup_segments = [s for s in result.segments if s.label == "WARMUP"]
    if warmup_segments:
        warmup_start = warmup_segments[0].start_time
        track_duration = beats[-1]
        warmup_position = warmup_start / track_duration
        print(f"  WARMUP starts at {warmup_start:.1f}s ({warmup_position:.1%} into track)")
        assert warmup_position < 0.5, f"WARMUP too late in track (position: {warmup_position:.1%})"

    print("  WARMUP detection working correctly!")

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("WARMUP Section Detection (F-005) - Verification")
    print("=" * 60)

    try:
        test_constants()
        test_segment_labels()
        test_warmup_detection()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
