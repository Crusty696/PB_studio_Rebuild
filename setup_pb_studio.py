#!/usr/bin/env python3
"""
PB Studio Rebuild — Setup Script
=================================
Migration 2026-04-27: bevorzugt conda-env "pb-studio" (Python 3.10 + CUDA 11.3,
kompatibel mit NVIDIA Treiber 461.40, Surface Book 2). Fallback auf .venv310.

Alternativ: python scripts/setup_py310_gpu.py [--skip-venv]
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
SETUP_SCRIPT = PROJECT_DIR / "scripts" / "setup_py310_gpu.py"


def _running_in_conda_env() -> bool:
    return bool(os.environ.get("CONDA_PREFIX")) or "conda" in sys.prefix.lower()


def main():
    print("=" * 50)
    print("  PB Studio Rebuild — Setup")
    print("=" * 50)

    if not SETUP_SCRIPT.exists():
        print(f"\n  FEHLER: {SETUP_SCRIPT} nicht gefunden!")
        sys.exit(1)

    cmd = [sys.executable, str(SETUP_SCRIPT)]
    if _running_in_conda_env():
        cmd.append("--skip-venv")
        print("  (conda-env erkannt: --skip-venv)")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
