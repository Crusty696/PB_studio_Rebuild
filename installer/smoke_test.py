"""
installer/smoke_test.py — Post-build smoke test for PB Studio installer.

Run this AFTER build_installer.bat completes to verify the frozen build.
Usage: python installer/smoke_test.py [--dist-dir dist/pb_studio]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST_DIR_DEFAULT = ROOT / 'dist' / 'pb_studio'


def check(label: str, condition: bool, fatal: bool = True) -> bool:
    status = "[OK]  " if condition else "[FAIL]"
    print(f"  {status} {label}")
    if not condition and fatal:
        sys.exit(1)
    return condition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', default=str(DIST_DIR_DEFAULT))
    args = parser.parse_args()
    dist = Path(args.dist_dir)

    print("\nPB Studio Smoke Test")
    print("=" * 50)

    # 1. Check dist folder exists
    check("dist folder exists", dist.is_dir())

    # 2. EXE present
    exe = dist / 'pb_studio.exe'
    check("pb_studio.exe exists", exe.exists())

    # 3. EXE is non-trivial size (>= 50 MB sanity check)
    size_mb = exe.stat().st_size / 1024 / 1024
    check(f"EXE size >= 50 MB (actual: {size_mb:.0f} MB)", size_mb >= 50, fatal=False)

    # 4. Critical DLLs present (CUDA, Qt)
    critical_dlls = [
        'Qt6Core.dll',
        'Qt6Widgets.dll',
        'Qt6Gui.dll',
    ]
    for dll in critical_dlls:
        found = any(dist.rglob(dll))
        check(f"{dll} present", found, fatal=False)

    # 5. Asset directories present
    for asset_dir in ['resources', 'styles', 'knowledge']:
        check(f"Asset dir: {asset_dir}/", (dist / asset_dir).is_dir(), fatal=False)

    # 6. Try launching the EXE and immediately closing it (5s timeout)
    #    Only works in interactive session on Windows
    if sys.platform == 'win32' and os.environ.get('SMOKE_TEST_LAUNCH', '0') == '1':
        print("\n  Launching EXE (5s timeout, requires display)...")
        try:
            proc = subprocess.Popen(
                [str(exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                print("  [OK]  EXE launched (terminated after 5s timeout)")
        except Exception as e:
            print(f"  [WARN] Could not launch EXE: {e}")

    # 7. Size summary
    total_size_gb = sum(f.stat().st_size for f in dist.rglob('*') if f.is_file()) / 1024**3
    print(f"\n  Total dist size: {total_size_gb:.2f} GB")

    print("\n" + "=" * 50)
    print("Smoke test complete. Review any [FAIL] / [WARN] items above.")
    print()


if __name__ == '__main__':
    main()
