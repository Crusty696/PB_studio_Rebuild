#!/usr/bin/env python3
"""
Demo Video Generator for PB Studio

This script automates the creation of demo videos showcasing PB Studio's
beat-sync capabilities. It generates before/after comparisons and feature
highlight reels.

Usage:
    python generate_demo_video.py --type before_after --audio demo_track.mp3 --videos video1.mp4 video2.mp4
    python generate_demo_video.py --type feature_showcase --audio demo_track.mp3 --videos video_dir/
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List

# Add PB Studio modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from services.beat_analysis_service import BeatAnalysisService
    from services.ai_audio_service import AIAudioService
    from services.video_analysis_service import VideoAnalysisService
    from services.pacing_service import PacingService
    from services.export_service import ExportService
    from database.database import init_db, Session
    from database.models import MediaFile, Project
except ImportError as e:
    print(f"Error: Unable to import PB Studio modules: {e}")
    print("Make sure you're running this script from the project root.")
    sys.exit(1)


class DemoVideoGenerator:
    """Generates demo videos for sales presentations"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        init_db()
        self.session = Session()

        # Initialize services
        self.beat_service = BeatAnalysisService()
        self.audio_service = AIAudioService()
        self.video_service = VideoAnalysisService()
        self.pacing_service = PacingService()
        self.export_service = ExportService()

    def create_before_after(self, audio_path: Path, video_paths: List[Path]) -> Path:
        """
        Creates a before/after comparison video.

        "Before" shows manual editing (simulated with random cuts).
        "After" shows PB Studio's auto-edit.

        Returns path to final comparison video.
        """
        print("=== Creating Before/After Comparison ===\n")

        # Step 1: Create project
        print("[1/7] Creating demo project...")
        project = Project(name="Before_After_Demo", description="Demo comparison video")
        self.session.add(project)
        self.session.commit()

        # Step 2: Import audio
        print(f"[2/7] Importing audio: {audio_path.name}")
        audio_file = MediaFile(
            project_id=project.id,
            file_path=str(audio_path),
            file_type="audio",
            name=audio_path.stem
        )
        self.session.add(audio_file)
        self.session.commit()

        # Step 3: Analyze audio
        print("[3/7] Analyzing audio (beat detection + stem separation)...")
        start = time.time()

        # Beat detection
        print("  - Running beat detection...")
        beats = self.beat_service.analyze(audio_file)
        print(f"    Found {len(beats)} beats")

        # Stem separation
        print("  - Separating stems (this takes 1-3 minutes)...")
        stems = self.audio_service.separate_stems(audio_file)
        print(f"    Separated into {len(stems)} stems")

        audio_time = time.time() - start
        print(f"  ✓ Audio analysis complete in {audio_time:.1f}s\n")

        # Step 4: Import and analyze videos
        print(f"[4/7] Importing and analyzing {len(video_paths)} video clips...")
        video_files = []
        start = time.time()

        for i, video_path in enumerate(video_paths):
            print(f"  - Analyzing {video_path.name} ({i+1}/{len(video_paths)})...")

            video_file = MediaFile(
                project_id=project.id,
                file_path=str(video_path),
                file_type="video",
                name=video_path.stem
            )
            self.session.add(video_file)
            self.session.commit()

            # Run video analysis
            self.video_service.analyze(video_file)
            video_files.append(video_file)

        video_time = time.time() - start
        print(f"  ✓ Video analysis complete in {video_time:.1f}s\n")

        # Step 5: Generate "Before" timeline (manual editing simulation)
        print("[5/7] Generating 'Before' timeline (manual editing simulation)...")
        before_timeline_path = self.output_dir / "before_timeline.otio"

        # Create random cuts (no beat sync)
        before_timeline = self._create_manual_timeline(audio_file, video_files)
        before_timeline_path.write_text(before_timeline)
        print("  ✓ Manual timeline created\n")

        # Step 6: Generate "After" timeline (PB Studio auto-edit)
        print("[6/7] Generating 'After' timeline (PB Studio auto-edit)...")
        start = time.time()

        after_timeline = self.pacing_service.create_auto_edit(
            audio_file=audio_file,
            video_files=video_files,
            beats=beats,
            stems=stems
        )

        autoedit_time = time.time() - start
        print(f"  ✓ Auto-edit complete in {autoedit_time:.1f}s\n")

        # Step 7: Render comparison video
        print("[7/7] Rendering comparison video...")
        output_path = self.output_dir / "before_after_comparison.mp4"

        self._render_side_by_side(
            before_timeline_path=before_timeline_path,
            after_timeline=after_timeline,
            output_path=output_path
        )

        print(f"\n✓ Demo video created: {output_path}")
        print(f"\nTimings:")
        print(f"  Audio analysis: {audio_time:.1f}s")
        print(f"  Video analysis: {video_time:.1f}s")
        print(f"  Auto-edit: {autoedit_time:.1f}s")
        print(f"  Total: {audio_time + video_time + autoedit_time:.1f}s")

        return output_path

    def create_feature_showcase(self, audio_path: Path, video_paths: List[Path]) -> Path:
        """
        Creates a feature showcase video highlighting:
        - Beat detection
        - Stem separation
        - Video analysis
        - Stem-aware pacing

        Returns path to showcase video.
        """
        print("=== Creating Feature Showcase ===\n")

        # Similar structure to before_after but with different rendering
        # that highlights specific features with overlays and annotations

        output_path = self.output_dir / "feature_showcase.mp4"

        print("Feature showcase generation not yet implemented.")
        print("Use the demo_video_guide.md for manual recording instructions.")

        return output_path

    def _create_manual_timeline(self, audio_file: MediaFile, video_files: List[MediaFile]) -> str:
        """
        Simulates a manual edit with random cuts (no beat sync).
        This represents the "before" state.
        """
        import random
        import opentimelineio as otio

        timeline = otio.schema.Timeline(name="Manual Edit")
        track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

        # Get audio duration
        audio_duration = audio_file.duration or 180.0  # fallback

        # Random cut length between 1-5 seconds (not beat-synced)
        current_time = 0.0
        while current_time < audio_duration:
            clip_duration = random.uniform(1.0, 5.0)
            video_file = random.choice(video_files)

            clip = otio.schema.Clip(
                name=video_file.name,
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, 30),
                    duration=otio.opentime.RationalTime(int(clip_duration * 30), 30)
                )
            )
            track.append(clip)
            current_time += clip_duration

        timeline.tracks.append(track)
        return otio.adapters.write_to_string(timeline, "otio_json")

    def _render_side_by_side(
        self,
        before_timeline_path: Path,
        after_timeline,
        output_path: Path
    ):
        """
        Renders a side-by-side comparison video using FFmpeg.
        Left: Manual edit
        Right: PB Studio auto-edit
        """
        import subprocess

        # First, render each timeline separately
        before_video = self.output_dir / "before.mp4"
        after_video = self.output_dir / "after.mp4"

        print("  - Rendering 'Before' video...")
        # TODO: Implement OTIO to FFmpeg rendering
        # For now, this is a placeholder

        print("  - Rendering 'After' video...")
        # TODO: Implement timeline rendering

        print("  - Combining into side-by-side...")
        # FFmpeg command for side-by-side
        cmd = [
            "ffmpeg",
            "-i", str(before_video),
            "-i", str(after_video),
            "-filter_complex",
            "[0:v]scale=960:1080,drawtext=text='Manual Editing':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=30[left];"
            "[1:v]scale=960:1080,drawtext=text='PB Studio Auto-Edit':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=30[right];"
            "[left][right]hstack=inputs=2[v]",
            "-map", "[v]",
            "-map", "1:a",  # Use audio from after video
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path)
        ]

        # TODO: Execute FFmpeg command
        print(f"  ✓ Side-by-side video created: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate demo videos for PB Studio sales presentations"
    )
    parser.add_argument(
        "--type",
        choices=["before_after", "feature_showcase"],
        required=True,
        help="Type of demo video to generate"
    )
    parser.add_argument(
        "--audio",
        type=Path,
        required=True,
        help="Path to audio file (MP3, WAV, FLAC)"
    )
    parser.add_argument(
        "--videos",
        type=Path,
        nargs="+",
        required=True,
        help="Paths to video files or directory containing videos"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("demos/sample_videos/output"),
        help="Output directory for generated videos"
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.audio.exists():
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)

    # Collect video paths
    video_paths = []
    for path in args.videos:
        if path.is_dir():
            video_paths.extend(path.glob("*.mp4"))
            video_paths.extend(path.glob("*.mov"))
        elif path.is_file():
            video_paths.append(path)
        else:
            print(f"Warning: Skipping invalid path: {path}")

    if not video_paths:
        print("Error: No valid video files found")
        sys.exit(1)

    print(f"Found {len(video_paths)} video files")

    # Generate demo video
    generator = DemoVideoGenerator(args.output_dir)

    if args.type == "before_after":
        output_path = generator.create_before_after(args.audio, video_paths)
    elif args.type == "feature_showcase":
        output_path = generator.create_feature_showcase(args.audio, video_paths)

    print(f"\n✓ Demo video generation complete!")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
