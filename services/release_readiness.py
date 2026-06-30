"""Production release-readiness blockers beyond deferred gates.

This module is intentionally conservative. Missing proof blocks a release.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import subprocess
import sys


@dataclass(frozen=True)
class ReleaseBlocker:
    blocker_id: str
    label: str
    detail: str


def production_blockers(repo_root: str | Path) -> list[ReleaseBlocker]:
    root = Path(repo_root)
    blockers: list[ReleaseBlocker] = []
    blockers.extend(_artifact_blockers(root))
    blockers.extend(_proof_blockers(root))
    return blockers


def _artifact_blockers(root: Path) -> list[ReleaseBlocker]:
    dist = root / "dist" / "pb_studio"
    installer = root / "dist" / "pb_studio_setup_v0.5.0.exe"
    payload = root / "dist" / "pb_studio_setup_v0.5.0.nsisbin"
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

    if installer.is_file():
        signature = _authenticode_status(installer)
        if signature != "Valid":
            blockers.append(
                ReleaseBlocker(
                    "SIGN-001",
                    "Installer is not code-signed",
                    f"{installer} Authenticode={signature}",
                )
            )
    return blockers


def _proof_blockers(root: Path) -> list[ReleaseBlocker]:
    synthesis = root / "docs" / "superpowers" / "synthesis"
    blockers: list[ReleaseBlocker] = []
    if not _has_matching_proof(synthesis, ("clean-vm", "install")):
        blockers.append(
            ReleaseBlocker(
                "VM-001",
                "Clean Windows VM install proof missing",
                "Need synthesis proof for installer run on clean Windows 11 VM without dev Python.",
            )
        )
    if not _has_matching_proof(synthesis, ("installed-app", "gui")):
        blockers.append(
            ReleaseBlocker(
                "GUI-001",
                "Installed-app full GUI workflow proof missing",
                "Need synthesis proof from installed app, not dist-folder smoke.",
            )
        )
    return blockers


def _has_matching_proof(folder: Path, needles: tuple[str, ...]) -> bool:
    if not folder.is_dir():
        return False
    for path in folder.glob("*.md"):
        name = path.name.lower()
        if all(needle in name for needle in needles):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            if "pass" in text and "release_ready" not in text:
                return True
    return False


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
