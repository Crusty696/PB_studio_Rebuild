#!/usr/bin/env python3
"""
pre_cache_models.py — Download and cache AI models for offline PB Studio deployment

This script downloads all required AI models to a local cache directory,
enabling offline installation and deployment of PB Studio.

Usage:
    python installer/pre_cache_models.py
    python installer/pre_cache_models.py --cache-dir D:\Models\huggingface
    python installer/pre_cache_models.py --token hf_your_token_here

Requirements:
    pip install huggingface_hub tqdm
"""

import os
import sys
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download
from tqdm import tqdm


def get_hf_token():
    """Get Hugging Face token from environment or prompt user."""
    token = os.environ.get("HUGGINGFACE_API_TOKEN")
    if not token:
        token = os.environ.get("HF_TOKEN")

    if not token:
        print("\n" + "=" * 60)
        print("Hugging Face Token Required")
        print("=" * 60)
        print("\nTo download AI models, you need a Hugging Face account and token.")
        print("\n1. Create account: https://huggingface.co/join")
        print("2. Create token: https://huggingface.co/settings/tokens")
        print("   - Token type: Read")
        print("   - Token name: PB Studio Model Cache")
        print("\n" + "=" * 60)

        token = input("\nEnter your Hugging Face token (hf_...): ").strip()

        if not token.startswith("hf_"):
            print("\n[ERROR] Invalid token format. Token must start with 'hf_'")
            sys.exit(1)

    return token


def download_model(repo_id, cache_dir, token, description):
    """Download a single model with progress bar."""
    print(f"\n{'=' * 60}")
    print(f"Downloading: {description}")
    print(f"Repository: {repo_id}")
    print(f"Cache: {cache_dir}")
    print(f"{'=' * 60}\n")

    try:
        # huggingface_hub >= 0.23: resume_download ist Default-Verhalten,
        # der Parameter ist deprecated und wird in 1.0.0 entfernt.
        # force_download=True wuerde stattdessen einen Fresh-Download erzwingen.
        snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            token=token,
            local_files_only=False,
        )
        print(f"\n✓ {description} downloaded successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Failed to download {description}")
        print(f"Error: {e}")
        return False


def verify_cache(cache_dir, models):
    """Verify that all models are cached."""
    print(f"\n{'=' * 60}")
    print("Verifying Cached Models")
    print(f"{'=' * 60}\n")

    cache_path = Path(cache_dir)
    all_found = True

    for model_info in models:
        repo_id = model_info["repo_id"]
        description = model_info["description"]

        # Convert repo_id to cache path format
        # e.g., "facebook/htdemucs" -> "models--facebook--htdemucs"
        model_cache_name = "models--" + repo_id.replace("/", "--")
        model_cache_path = cache_path / model_cache_name

        if model_cache_path.exists():
            # Count files in cache
            files = list(model_cache_path.rglob("*"))
            file_count = len([f for f in files if f.is_file()])

            print(f"✓ {description}")
            print(f"  Path: {model_cache_path}")
            print(f"  Files: {file_count}")
        else:
            print(f"✗ {description} - NOT FOUND")
            all_found = False

        print()

    return all_found


def get_cache_size(cache_dir):
    """Calculate total cache size."""
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return 0

    total_size = 0
    for file in cache_path.rglob("*"):
        if file.is_file():
            total_size += file.stat().st_size

    return total_size


def format_size(size_bytes):
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def main():
    parser = argparse.ArgumentParser(
        description="Download and cache AI models for PB Studio offline deployment"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Cache directory (default: %USERPROFILE%\\.cache or HF_HOME env var)"
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Hugging Face API token (default: from env HUGGINGFACE_API_TOKEN)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing cache, don't download"
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip verification after download"
    )

    args = parser.parse_args()

    # Determine cache directory
    if args.cache_dir:
        cache_dir = args.cache_dir
    elif "HF_HOME" in os.environ:
        cache_dir = os.environ["HF_HOME"]
    else:
        cache_dir = str(Path.home() / ".cache")

    cache_dir = str(Path(cache_dir).resolve())

    # Get token (only if not verify-only)
    if not args.verify_only:
        if args.token:
            token = args.token
        else:
            token = get_hf_token()
    else:
        token = None

    # Define models to cache
    models = [
        {
            "repo_id": "facebook/htdemucs",
            "description": "Demucs (Audio Stem Separation)",
            "size_estimate": "~300 MB"
        },
        {
            "repo_id": "google/siglip-so400m-patch14-384",
            "description": "SigLIP (Visual Understanding)",
            "size_estimate": "~1.8 GB"
        },
        {
            "repo_id": "vikhyatk/moondream2",
            "description": "Moondream2 (Visual LLM)",
            "size_estimate": "~1.7 GB"
        },
        {
            "repo_id": "CPJKU/beat_this",
            "description": "beat_this (Beat Detection)",
            "size_estimate": "~200 MB"
        },
    ]

    # Print header
    print("\n" + "=" * 60)
    print("PB Studio Model Cache Utility")
    print("=" * 60)
    print(f"\nCache Directory: {cache_dir}")
    print(f"Models to cache: {len(models)}")
    print(f"Estimated download: ~5.7 GB")
    print(f"Time estimate: 15-45 minutes (depending on connection)")

    # Create cache directory if it doesn't exist
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # Verify only mode
    if args.verify_only:
        verify_cache(cache_dir, models)
        return

    # Download models
    print("\n" + "=" * 60)
    print("Starting Download")
    print("=" * 60)

    success_count = 0
    for i, model_info in enumerate(models, 1):
        print(f"\n[{i}/{len(models)}] ", end="")

        success = download_model(
            repo_id=model_info["repo_id"],
            cache_dir=cache_dir,
            token=token,
            description=model_info["description"]
        )

        if success:
            success_count += 1

    # Verify cache (unless skipped)
    if not args.skip_verify:
        all_cached = verify_cache(cache_dir, models)
    else:
        all_cached = True

    # Calculate cache size
    cache_size = get_cache_size(cache_dir)

    # Print summary
    print("=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Successful: {success_count}/{len(models)}")
    print(f"Cache directory: {cache_dir}")
    print(f"Total cache size: {format_size(cache_size)}")

    if all_cached and success_count == len(models):
        print("\n✓ All models cached successfully!")
        print("\nNext steps:")
        print("1. Set HF_HOME environment variable to this cache directory")
        print("2. Or copy this cache to target deployment machines")
        print(f"   Target path: %USERPROFILE%\\.cache")
        print("\n3. Enable offline mode in PB Studio:")
        print("   Set OFFLINE_MODE=1 in config.env")
    else:
        print("\n⚠ Some models failed to download or verify")
        print("Check errors above and retry")
        sys.exit(1)

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Download interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
