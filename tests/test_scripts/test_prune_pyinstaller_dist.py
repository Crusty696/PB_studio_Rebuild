from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "installer" / "prune_pyinstaller_dist.py"


def test_prune_keeps_loader_vc_runtime_dlls(tmp_path: Path) -> None:
    internal = tmp_path / "pb_studio" / "_internal"
    pyside = internal / "PySide6"
    pyside.mkdir(parents=True)

    root_runtime = internal / "vcruntime140.dll"
    nested_runtime = pyside / "vcruntime140.dll"
    root_zlib = internal / "zlib.dll"
    nested_zlib = pyside / "zlib.dll"
    root_duplicate = internal / "Qt6Core.dll"
    nested_duplicate = pyside / "Qt6Core.dll"
    for path in (root_runtime, nested_runtime, root_zlib, nested_zlib, root_duplicate, nested_duplicate):
        path.write_bytes(b"dll")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dist-dir", str(tmp_path / "pb_studio")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert root_runtime.exists()
    assert nested_runtime.exists()
    assert root_zlib.exists()
    assert nested_zlib.exists()
    assert not root_duplicate.exists()
    assert nested_duplicate.exists()
