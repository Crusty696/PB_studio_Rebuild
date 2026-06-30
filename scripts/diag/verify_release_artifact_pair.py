from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "release_artifact_pair_audit.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _match(pattern: str, text: str) -> str | None:
    found = re.search(pattern, text, re.MULTILINE)
    return found.group(1) if found else None


def _glob_exists(root: Path, pattern: str) -> bool:
    return any(root.rglob(pattern))


def _authenticode_status(path: Path) -> dict[str, str | bool]:
    if sys.platform != "win32":
        return {"checked": False, "status": "not-windows", "signed": False}
    ps_path = json.dumps(str(path))
    shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
    command = [
        shell,
        "-NoProfile",
        "-Command",
        f"(Get-AuthenticodeSignature -LiteralPath {ps_path}).Status",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    status = proc.stdout.strip() or proc.stderr.strip() or f"exit-{proc.returncode}"
    return {"checked": proc.returncode == 0, "status": status, "signed": status == "Valid"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", default=str(ROOT / "dist" / "pb_studio"))
    parser.add_argument("--installer-exe", default=str(ROOT / "dist" / "pb_studio_setup_v0.5.0.exe"))
    parser.add_argument("--installer-payload", default=str(ROOT / "dist" / "pb_studio_setup_v0.5.0.nsisbin"))
    args = parser.parse_args()

    dist = Path(args.dist_dir)
    installer_exe = Path(args.installer_exe)
    installer_payload = Path(args.installer_payload)
    app_exe = dist / "pb_studio.exe"

    pyproject = _read(ROOT / "pyproject.toml")
    nsi = _read(ROOT / "installer" / "pb_studio.nsi")
    build_bat = _read(ROOT / "installer" / "build_installer.bat")
    version_info = _read(ROOT / "installer" / "version_info.txt")
    readme = _read(ROOT / "README.md")

    versions = {
        "pyproject": _match(r'^version\s*=\s*"([^"]+)"', pyproject),
        "nsi": _match(r'!define APP_VERSION\s+"([^"]+)"', nsi),
        "build_installer": _match(r"set APP_VERSION=([0-9.]+)", build_bat),
        "version_info_file": _match(r"FileVersion', u'([0-9.]+)'", version_info),
        "version_info_product": _match(r"ProductVersion', u'([0-9.]+)'", version_info),
        "readme": _match(r"\*\*v([0-9.]+)\*\*", readme),
    }
    normalized_versions = {
        key: value[:-2] if value and value.endswith(".0") and value.count(".") == 3 else value
        for key, value in versions.items()
    }
    expected_version = "0.5.0"

    required_dist_patterns = {
        "pb_studio.exe": app_exe.exists(),
        "Qt6Core.dll": _glob_exists(dist, "Qt6Core.dll"),
        "Qt6Gui.dll": _glob_exists(dist, "Qt6Gui.dll"),
        "Qt6Widgets.dll": _glob_exists(dist, "Qt6Widgets.dll"),
        "torch_cuda.dll": _glob_exists(dist, "torch_cuda.dll"),
        "cudart": _glob_exists(dist, "cudart*.dll"),
        "cublas": _glob_exists(dist, "cublas*.dll"),
        "cudnn": _glob_exists(dist, "cudnn*.dll"),
        "ffmpeg.exe": _glob_exists(dist, "ffmpeg.exe"),
        "ffprobe.exe": _glob_exists(dist, "ffprobe.exe"),
        "resources": (dist / "resources").is_dir() or (dist / "_internal" / "resources").is_dir(),
        "knowledge": (dist / "knowledge").is_dir() or (dist / "_internal" / "knowledge").is_dir(),
        "config": (dist / "config").is_dir() or (dist / "_internal" / "config").is_dir(),
        "translations": (dist / "translations").is_dir() or (dist / "_internal" / "translations").is_dir(),
    }

    installer_resources = {
        "pb_studio.ico": (ROOT / "resources" / "pb_studio.ico").exists(),
        "installer_header.bmp": (ROOT / "resources" / "installer_header.bmp").exists(),
        "installer_welcome.bmp": (ROOT / "resources" / "installer_welcome.bmp").exists(),
        "license": (ROOT / "LICENSE.txt").exists(),
    }

    installer_pair_exists = installer_exe.is_file() and installer_payload.is_file()
    hashes = {}
    if installer_exe.is_file():
        hashes["installer_exe_sha256"] = _sha256(installer_exe)
    if installer_payload.is_file():
        hashes["installer_payload_sha256"] = _sha256(installer_payload)
    if app_exe.is_file():
        hashes["frozen_app_exe_sha256"] = _sha256(app_exe)

    unsigned_status = _authenticode_status(installer_exe) if installer_exe.exists() else {
        "checked": False,
        "status": "missing",
        "signed": False,
    }

    dist_size_bytes = sum(path.stat().st_size for path in dist.rglob("*") if path.is_file()) if dist.is_dir() else 0
    release_blockers = []
    if not unsigned_status["signed"]:
        release_blockers.append("installer-not-code-signed")
    release_blockers.extend(
        [
            "clean-vm-install-not-proven-by-this-audit",
            "installed-app-full-gui-workflow-not-proven-by-this-audit",
            "dg001-h1-replacement-medium-user-decision-open",
        ]
    )

    hard_checks = {
        "versions_match_0_5_0": all(value == expected_version for value in normalized_versions.values()),
        "dist_exists": dist.is_dir(),
        "installer_pair_exists": installer_pair_exists,
        "installer_payload_large_enough": installer_payload.is_file() and installer_payload.stat().st_size > 1024**3,
        "installer_stub_nonempty": installer_exe.is_file() and installer_exe.stat().st_size > 100_000,
        "dist_size_large_enough": dist_size_bytes > 1024**3,
        "required_dist_patterns_present": all(required_dist_patterns.values()),
        "installer_resources_present": all(installer_resources.values()),
    }

    result = {
        "status": "pass" if all(hard_checks.values()) else "fail",
        "release_ready": False,
        "expected_version": expected_version,
        "versions_raw": versions,
        "versions_normalized": normalized_versions,
        "dist_dir": str(dist),
        "dist_size_bytes": dist_size_bytes,
        "installer_exe": {
            "path": str(installer_exe),
            "exists": installer_exe.is_file(),
            "size_bytes": installer_exe.stat().st_size if installer_exe.is_file() else 0,
        },
        "installer_payload": {
            "path": str(installer_payload),
            "exists": installer_payload.is_file(),
            "size_bytes": installer_payload.stat().st_size if installer_payload.is_file() else 0,
        },
        "required_dist_patterns": required_dist_patterns,
        "installer_resources": installer_resources,
        "authenticode": unsigned_status,
        "hashes": hashes,
        "hard_checks": hard_checks,
        "release_blockers": release_blockers,
        "note": "Audit verifies artifact pair and runtime contents only; it does not prove clean-VM install or installed-app GUI workflow.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
