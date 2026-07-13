from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "config" / "ffmpeg_identity.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _version_line(path: Path) -> str:
    result = subprocess.run(
        [str(path), "-version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").splitlines()[0] if result.stdout else ""


def _default_paths() -> dict[str, Path]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin

    return {
        "ffmpeg": Path(get_ffmpeg_bin()),
        "ffprobe": Path(get_ffprobe_bin()),
    }


def verify_identity(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    resolved_paths: Mapping[str, Path] | None = None,
    probe_versions: bool = True,
) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    expected_version = str(manifest["version"])
    paths = dict(resolved_paths or _default_paths())
    payload: dict = {
        "ok": True,
        "expected_version": expected_version,
        "manifest": str(Path(manifest_path).resolve()),
        "tools": {},
    }

    for tool in ("ffmpeg", "ffprobe"):
        path = Path(paths[tool]).expanduser()
        expected_sha = str(manifest["tools"][tool]["sha256"]).upper()
        exists = path.is_file()
        actual_sha = _sha256(path) if exists else ""
        version_line = _version_line(path) if exists and probe_versions else ""
        sha_ok = exists and actual_sha == expected_sha
        version_ok = (not probe_versions) or (
            exists and expected_version in version_line
        )
        tool_ok = exists and sha_ok and version_ok
        payload["tools"][tool] = {
            "path": str(path.resolve()) if exists else str(path),
            "exists": exists,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "sha256_ok": sha_ok,
            "version_line": version_line,
            "version_ok": version_ok,
            "ok": tool_ok,
        }
        payload["ok"] = payload["ok"] and tool_ok

    return payload


def main() -> int:
    try:
        payload = verify_identity()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
