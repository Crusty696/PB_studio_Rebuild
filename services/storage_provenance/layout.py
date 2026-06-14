from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class StorageLayout:
    """Content-addressed storage layout rooted at ``storage/``."""

    def __init__(self, storage_root: str | Path) -> None:
        self.storage_root = Path(storage_root)

    @staticmethod
    def validate_sha256(source_sha256: str) -> str:
        if not _SHA256_RE.match(source_sha256):
            raise ValueError(f"Invalid source_sha256: {source_sha256!r}")
        return source_sha256.lower()

    def source_root(self, source_sha256: str) -> Path:
        sha = self.validate_sha256(source_sha256)
        return self.storage_root / "by_sha" / sha[:2] / sha

    def ensure_source_root(self, source_sha256: str) -> Path:
        root = self.source_root(source_sha256)
        (root / "audio").mkdir(parents=True, exist_ok=True)
        (root / "video").mkdir(parents=True, exist_ok=True)
        return root

    def relative_artifact_path(self, source_sha256: str, artifact_path: str | Path) -> str:
        root = self.source_root(source_sha256).absolute()
        artifact = Path(artifact_path).absolute()
        try:
            rel = artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Artifact path is outside source root: {artifact}") from exc
        return rel.as_posix()


def create_directory_link(link_path: str | Path, target_dir: str | Path) -> Path:
    """Create a Windows junction or POSIX symlink for a directory."""

    link = Path(link_path)
    target = Path(target_dir)
    if not target.is_dir():
        raise FileNotFoundError(f"Directory link target missing: {target}")

    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        if not link.is_dir():
            raise FileExistsError(f"Link path exists and is not a directory: {link}")
        return link

    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(
                f"mklink /J failed for {link} -> {target}: "
                f"{result.stdout.strip()} {result.stderr.strip()}".strip()
            )
    else:
        link.symlink_to(target, target_is_directory=True)
    return link
