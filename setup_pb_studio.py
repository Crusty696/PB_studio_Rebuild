#!/usr/bin/env python3
"""
PB Studio Rebuild — Setup Script
=================================
Erstellt .venv310 mit Python 3.10 + torch 1.12.1+cu113
(kompatibel mit NVIDIA Treiber 461.40, Surface Book 2).

Alternativ: python scripts/setup_py310_gpu.py (gleiches Ergebnis)
"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
SETUP_SCRIPT = PROJECT_DIR / "scripts" / "setup_py310_gpu.py"


def main():
    print("=" * 50)
    print("  PB Studio Rebuild — Setup")
    print("=" * 50)

    if not SETUP_SCRIPT.exists():
        print(f"\n  FEHLER: {SETUP_SCRIPT} nicht gefunden!")
        sys.exit(1)

    # Delegiere an das GPU-Setup-Skript
    result = subprocess.run(
        [sys.executable, str(SETUP_SCRIPT)],
        cwd=str(PROJECT_DIR),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
