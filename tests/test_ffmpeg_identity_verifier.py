from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _manifest(path, ffmpeg_bytes: bytes, ffprobe_bytes: bytes):
    payload = {
        "version": "6.1.1",
        "tools": {
            "ffmpeg": {
                "filename": "ffmpeg.exe",
                "sha256": hashlib.sha256(ffmpeg_bytes).hexdigest().upper(),
            },
            "ffprobe": {
                "filename": "ffprobe.exe",
                "sha256": hashlib.sha256(ffprobe_bytes).hexdigest().upper(),
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_identity_verifier_accepts_matching_pair(tmp_path):
    from tools.verify_ffmpeg_identity import verify_identity

    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"ffmpeg-v6")
    ffprobe.write_bytes(b"ffprobe-v6")
    manifest = _manifest(tmp_path / "manifest.json", b"ffmpeg-v6", b"ffprobe-v6")

    result = verify_identity(
        manifest_path=manifest,
        resolved_paths={"ffmpeg": ffmpeg, "ffprobe": ffprobe},
        probe_versions=False,
    )

    assert result["ok"] is True
    assert result["tools"]["ffmpeg"]["sha256_ok"] is True
    assert result["tools"]["ffprobe"]["sha256_ok"] is True


def test_identity_verifier_rejects_hash_drift_and_missing_tool(tmp_path):
    from tools.verify_ffmpeg_identity import verify_identity

    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"wrong")
    manifest = _manifest(tmp_path / "manifest.json", b"expected", b"expected-probe")

    result = verify_identity(
        manifest_path=manifest,
        resolved_paths={
            "ffmpeg": ffmpeg,
            "ffprobe": tmp_path / "missing-ffprobe.exe",
        },
        probe_versions=False,
    )

    assert result["ok"] is False
    assert result["tools"]["ffmpeg"]["sha256_ok"] is False
    assert result["tools"]["ffprobe"]["exists"] is False


def test_agent_start_blocks_on_ffmpeg_identity_drift():
    source = (Path(__file__).parents[1] / "tools" / "agent_start.ps1").read_text(
        encoding="utf-8"
    )
    assert "verify_ffmpeg_identity.py" in source
    assert "FFmpeg Identity" in source
    assert "BLOCKED: canonical FFmpeg identity verification failed" in source


def test_pyinstaller_spec_resolves_ignored_binaries_from_git_common_root():
    source = (Path(__file__).parents[1] / "pb_studio.spec").read_text(
        encoding="utf-8"
    )
    assert "def _resolve_packaged_binary" in source
    assert "commondir" in source
    assert "_resolve_packaged_binary('ffmpeg.exe')" in source
    assert "_resolve_packaged_binary('ffprobe.exe')" in source
