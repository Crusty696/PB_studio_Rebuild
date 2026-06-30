"""
installer/smoke_test.py — Post-build smoke test for PB Studio installer.

Run this AFTER build_installer.bat completes to verify the frozen build.
Usage: python installer/smoke_test.py [--dist-dir dist/pb_studio]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST_DIR_DEFAULT = ROOT / 'dist' / 'pb_studio'
failures: list[str] = []


def check(label: str, condition: bool, fatal: bool = True) -> bool:
    status = "[OK]  " if condition else "[FAIL]"
    print(f"  {status} {label}")
    if not condition:
        failures.append(label)
        if fatal:
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

    # 3. EXE is non-trivial size. PyInstaller 6 onedir keeps payload under
    # _internal, so the launcher EXE is smaller than the full application.
    size_mb = exe.stat().st_size / 1024 / 1024
    check(f"EXE size >= 10 MB (actual: {size_mb:.0f} MB)", size_mb >= 10, fatal=False)

    # 4. Critical DLLs present (CUDA, Qt, Torch)
    critical_dlls = [
        'Qt6Core.dll',
        'Qt6Widgets.dll',
        'Qt6Gui.dll',
    ]
    for dll in critical_dlls:
        found = any(dist.rglob(dll))
        check(f"{dll} present", found, fatal=False)

    # 4b. CUDA / Torch runtime DLLs (B-430)
    cuda_torch_dlls = [
        'torch_cuda*.dll',
        'cudart*.dll',
        'cublas*.dll',
        'cudnn*.dll',
    ]
    for pattern in cuda_torch_dlls:
        found = any(dist.rglob(pattern))
        check(f"CUDA/Torch DLL pattern '{pattern}' present", found, fatal=False)

    # 5. Asset directories present.
    # B-437: PyInstaller 6 (onedir) legt Daten unter dist/pb_studio/_internal/ ab,
    # nicht mehr im Top-Level. 'styles' wurde bei Repo-Bereinigung entfernt (Theme
    # kommt aus ui/theme.py) -> nicht mehr pruefen.
    def _dir_present(name):
        return (dist / name).is_dir() or (dist / '_internal' / name).is_dir()
    for asset_dir in ['resources', 'knowledge']:
        check(f"Asset dir: {asset_dir}/", _dir_present(asset_dir), fatal=False)

    # 5b. Additional runtime directories (B-430)
    for extra_dir in ['config', 'translations']:
        check(f"Runtime dir: {extra_dir}/", _dir_present(extra_dir), fatal=False)

    # 5c. FFmpeg / ffprobe binaries (B-430)
    for ffbin in ['ffmpeg.exe', 'ffprobe.exe']:
        found = (dist / 'bin' / ffbin).exists() or any(dist.rglob(ffbin))
        check(f"FFmpeg binary: {ffbin}", found, fatal=False)

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
            else:
                stdout = (proc.stdout.read() if proc.stdout else b"").decode(errors="replace").strip()
                stderr = (proc.stderr.read() if proc.stderr else b"").decode(errors="replace").strip()
                if stdout:
                    print(f"  [INFO] launch stdout: {stdout[-500:]}")
                if stderr:
                    print(f"  [INFO] launch stderr: {stderr[-500:]}")
                check("EXE stayed alive for 5s launch smoke", False, fatal=False)
        except Exception as e:
            print(f"  [WARN] Could not launch EXE: {e}")

    if sys.platform == 'win32' and os.environ.get('SMOKE_TEST_FROZEN_AUDIO', '0') == '1':
        print("\n  Running frozen audio smoke...")
        with tempfile.TemporaryDirectory(prefix='pb_frozen_audio_smoke_') as tmp:
            out_path = Path(tmp) / 'audio_smoke.json'
            env = os.environ.copy()
            env['PB_FROZEN_AUDIO_SMOKE'] = '1'
            env['PB_FROZEN_AUDIO_SMOKE_OUT'] = str(out_path)
            proc = subprocess.run(
                [str(exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                env=env,
            )
            print(f"  [INFO] frozen audio smoke exit={proc.returncode}")
            if proc.stdout.strip():
                print(f"  [INFO] stdout: {proc.stdout.strip()[:500]}")
            if proc.stderr.strip():
                print(f"  [INFO] stderr: {proc.stderr.strip()[:500]}")
            check("frozen audio smoke process exit 0", proc.returncode == 0, fatal=False)
            check("frozen audio smoke artifact exists", out_path.exists(), fatal=False)
            if out_path.exists():
                payload = json.loads(out_path.read_text(encoding='utf-8'))
                check("frozen audio smoke passed", bool(payload.get('passed')), fatal=False)
                check("frozen audio smoke ran inside frozen exe", bool(payload.get('frozen')), fatal=False)
                checks = payload.get('checks') or {}
                check("frozen audio smoke found ffmpeg", bool(checks.get('ffmpeg_exists')), fatal=False)
                shape = checks.get('shape') or []
                check(
                    "frozen audio smoke returned stereo waveform",
                    len(shape) == 2 and shape[0] == 2 and shape[1] > 0,
                    fatal=False,
                )

    # 7. Size summary
    total_size_gb = sum(f.stat().st_size for f in dist.rglob('*') if f.is_file()) / 1024**3
    print(f"\n  Total dist size: {total_size_gb:.2f} GB")
    check(f"Total dist size >= 1 GB (actual: {total_size_gb:.2f} GB)", total_size_gb >= 1, fatal=False)

    print("\n" + "=" * 50)
    if failures:
        print("Smoke test failed:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)
    print("Smoke test passed.")
    print()


if __name__ == '__main__':
    main()
