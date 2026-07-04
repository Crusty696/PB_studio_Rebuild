"""Production release-readiness blockers beyond deferred gates.

This module is intentionally conservative. Missing proof blocks a release.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import subprocess
import sys

_RELEASE_RELEVANT_PATHS = (
    "main.py",
    "app.py",
    "config",
    "core",
    "database",
    "installer",
    "knowledge",
    "models",
    "resources",
    "services",
    "ui",
    "workers",
    "pb_studio.spec",
    "pyproject.toml",
    "requirements.txt",
    "requirements.lock",
)


@dataclass(frozen=True)
class ReleaseBlocker:
    blocker_id: str
    label: str
    detail: str


@dataclass(frozen=True)
class _RelevantCommit:
    commit_hash: str
    timestamp: int
    iso_date: str
    subject: str


def production_blockers(repo_root: str | Path) -> list[ReleaseBlocker]:
    root = Path(repo_root)
    blockers: list[ReleaseBlocker] = []
    blockers.extend(_artifact_blockers(root))
    blockers.extend(_proof_blockers(root))
    return blockers


def _artifact_blockers(root: Path) -> list[ReleaseBlocker]:
    dist = root / "dist" / "pb_studio"
    frozen_exe = dist / "pb_studio.exe"
    installer = root / "dist" / "pb_studio_setup_v0.5.0.exe"
    payload = root / "dist" / "pb_studio_setup_v0.5.0.nsisbin"
    distribution_zip = root / "dist" / "PB_Studio_v0.5.0_distribution.zip"
    blockers: list[ReleaseBlocker] = []

    if not dist.is_dir():
        blockers.append(ReleaseBlocker("ART-001", "Frozen app folder missing", str(dist)))
    if not installer.is_file():
        blockers.append(ReleaseBlocker("ART-002", "Installer stub missing", str(installer)))
    if not payload.is_file():
        blockers.append(ReleaseBlocker("ART-003", "NSISBI payload missing", str(payload)))
    elif payload.stat().st_size <= 1024**3:
        blockers.append(
            ReleaseBlocker(
                "ART-004",
                "NSISBI payload too small for current CUDA bundle",
                f"{payload} size={payload.stat().st_size}",
            )
        )

    # Private/local distribution policy (user decision 2026-07-04):
    # Authenticode is optional and must not block release readiness.
    dirty_paths = _release_relevant_dirty_paths(root)
    if dirty_paths:
        blockers.append(
            ReleaseBlocker(
                "ART-006",
                "Release-relevant source has uncommitted changes",
                (
                    "Current frozen artifacts cannot be proven to contain local "
                    "release-relevant changes: "
                    + "; ".join(dirty_paths[:20])
                ),
            )
        )
    blockers.extend(
        _artifact_freshness_blockers(
            root,
            artifacts=[frozen_exe, installer, payload, distribution_zip],
        )
    )
    return blockers


def _release_relevant_dirty_paths(root: Path) -> list[str]:
    git = shutil.which("git")
    if not git:
        return []
    proc = subprocess.run(
        [
            git,
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *_RELEASE_RELEVANT_PATHS,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return []
    dirty: list[str] = []
    for line in proc.stdout.splitlines():
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if path:
            dirty.append(path)
    return dirty


def _artifact_freshness_blockers(root: Path, artifacts: list[Path]) -> list[ReleaseBlocker]:
    existing_artifacts = [path for path in artifacts if path.is_file()]
    if not existing_artifacts:
        return []

    commit = _latest_release_relevant_commit(root)
    if commit is None:
        return [
            ReleaseBlocker(
                "ART-005",
                "Release artifact freshness could not be proven",
                "git log for release-relevant product paths returned no usable commit.",
            )
        ]

    stale = [path for path in existing_artifacts if path.stat().st_mtime + 1 < commit.timestamp]
    if not stale:
        return []

    stale_details = "; ".join(
        f"{path.relative_to(root)} mtime={_format_mtime(path)}" for path in stale
    )
    return [
        ReleaseBlocker(
            "ART-005",
            "Release artifacts are older than current release-relevant code",
            (
                f"latest release-relevant commit {commit.commit_hash[:12]} at {commit.iso_date} "
                f"({commit.subject}); stale artifacts: {stale_details}"
            ),
        )
    ]


def _latest_release_relevant_commit(root: Path) -> _RelevantCommit | None:
    git = shutil.which("git")
    if not git:
        return None
    proc = subprocess.run(
        [
            git,
            "log",
            "-1",
            "--format=%H%x09%ct%x09%cI%x09%s",
            "--",
            *_RELEASE_RELEVANT_PATHS,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return None
    line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    parts = line.split("\t", 3)
    if len(parts) != 4:
        return None
    try:
        timestamp = int(parts[1])
    except ValueError:
        return None
    return _RelevantCommit(
        commit_hash=parts[0],
        timestamp=timestamp,
        iso_date=parts[2],
        subject=parts[3],
    )


def _format_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _proof_blockers(root: Path) -> list[ReleaseBlocker]:
    synthesis = root / "docs" / "superpowers" / "synthesis"
    blockers: list[ReleaseBlocker] = []
    if not _has_matching_proof(synthesis, "clean-vm-install"):
        blockers.append(
            ReleaseBlocker(
                "VM-001",
                "Clean Windows VM install proof missing",
                "Need explicit release_gate_proof synthesis: proof_type=clean-vm-install, status=pass.",
            )
        )
    if not _has_matching_proof(synthesis, "installed-app-gui"):
        blockers.append(
            ReleaseBlocker(
                "GUI-001",
                "Installed-app full GUI workflow proof missing",
                "Need explicit release_gate_proof synthesis: proof_type=installed-app-gui, status=pass.",
            )
        )
    return blockers


def _has_matching_proof(folder: Path, proof_type: str) -> bool:
    if not folder.is_dir():
        return False
    for path in folder.glob("*.md"):
        proof = _frontmatter(path)
        if proof.get("release_gate_proof") != "true":
            continue
        if proof.get("proof_type") != proof_type:
            continue
        if proof.get("status") != "pass":
            continue
        if proof.get("evidence_level") != "live":
            continue
        return True
    return False


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or lines[0].strip().lstrip("\ufeff") != "---":
        return {}
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip().strip("'\"").lower()
    return values


def _authenticode_status(path: Path) -> str:
    if sys.platform != "win32":
        return "not-windows"
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        return "powershell-missing"
    command = [
        shell,
        "-NoProfile",
        "-Command",
        f"(Get-AuthenticodeSignature -LiteralPath {json.dumps(str(path))}).Status",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or f"exit-{proc.returncode}").strip()
    return proc.stdout.strip() or "empty-status"
