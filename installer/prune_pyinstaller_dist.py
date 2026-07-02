"""Prune duplicated top-level DLLs from a PyInstaller onedir build.

PyInstaller can copy Torch/CUDA DLLs twice:
1. into ``dist/pb_studio/_internal`` as dependency binaries
2. into package-local dirs such as ``torch/lib``

The package-local copy is the one Torch expects on Windows. The runtime hook
adds those dirs to PATH, so the duplicate top-level copy can be removed.
"""

from __future__ import annotations

import argparse
from pathlib import Path


KEEP_DIRS = (
    Path("torch/lib"),
    Path("torch/bin"),
    Path("torchvision"),
    Path("PySide6"),
    Path("cv2"),
    Path("numpy.libs"),
    Path("scipy.libs"),
)

SUFFIXES = {".dll", ".pyd"}
ROOT_KEEP_DLLS = {
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "zlib.dll",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist-dir",
        default=str(Path("dist") / "pb_studio"),
        help="PyInstaller onedir folder",
    )
    args = parser.parse_args()

    dist = Path(args.dist_dir)
    internal = dist / "_internal"
    if not internal.is_dir():
        raise SystemExit(f"_internal folder missing: {internal}")

    keep_by_name: dict[str, list[Path]] = {}
    for rel_dir in KEEP_DIRS:
        root = internal / rel_dir
        if not root.is_dir():
            continue
        for file_path in root.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in SUFFIXES:
                keep_by_name.setdefault(file_path.name.lower(), []).append(file_path)

    removed_count = 0
    removed_bytes = 0
    for file_path in internal.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() not in SUFFIXES:
            continue
        if file_path.name.lower() in ROOT_KEEP_DLLS:
            continue
        package_copies = keep_by_name.get(file_path.name.lower(), [])
        if not package_copies:
            continue
        removed_bytes += file_path.stat().st_size
        file_path.unlink()
        removed_count += 1
        print(f"[PRUNE] removed duplicate top-level DLL: {file_path.name}")

    print(f"[PRUNE] removed_count={removed_count} removed_bytes={removed_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
